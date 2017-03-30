import time
import json
import errno
import struct
import socket
import collections
from functools import partial

import numpy
import zmq
from zmq.eventloop import zmqstream, ioloop

from .red import ReconnectingRedis
from .common import REDIS_KEYS, INPUT_STREAM, OUTPUT_STREAM

__all__ = ['Application']

ioloop.install()


class Application(object):

    def __init__(self, name, config, setup_input=True, setup_output=True, verbose=False):
        """
        An user app instance.

        * name should be a string. It will be used to store app data on redis
          and to identify the app through the http server.
          Accessible through instance.name

        * config can be either a string or a dict, if it's a string
          json.load(open(config)) will be used.
          + If "output_stream" or "input_stream" keys are present, they
          must specify at least a "width" and "height" subkeys.
          + If "redis" key is present it will be used to configure the redis
          client.
          + The "settings" key must be used for holding settings specific
          to the app that can be updated while it's running.
          The app is free to use any other keys.
          Accessible through instance.config

        * verbose should be a boolean.
          Accessible through instance.verbose

        * if setup_input is True a SUB socket for the input stream will be
          configured for the topic framework.INPUT_STREAM using
          config["input_stream"]

        * if setup_output is True a PUB socket for the output stream will be
          configured using config["output_stream"]
        """
        config = config or {}
        self.name = name
        self.verbose = verbose
        if not isinstance(config, dict):
            # Load config from json file.
            config = json.load(open(config))
        self.config = config

        # List of redis channels to subscribe.
        sub_channels = []
        if self.name:
            sub_channels.append(REDIS_KEYS.APP_CHANNEL + self.name)

        self._input_callback = None

        if 'input_stream' in config:
            input_width = config['input_stream']['width']
            input_height = config['input_stream']['height']
            self._bgr_shape = (input_height, input_width, 3)
            self._depth_shape = (input_height, input_width)
            sub_channels.append(REDIS_KEYS.SYS_INPUT_CHANNEL)
        else:
            setup_input = False
            self._bgr_shape = None
            self._depth_shape = None
        self._bgr_dtype = 'uint8'
        self._depth_dtype = 'uint16'

        if 'output_stream' in config:
            output_width = config['output_stream']['width']
            output_height = config['output_stream']['height']
            self._bin_shape = (output_height, output_width)
            self._out_transition = config['output_stream'].get('transition', False)
        else:
            setup_output = False
            self._bin_shape = None
            self._out_transition = False
        self._bin_dtype = 'uint8'
        if self._out_transition and not self.name:
            raise ValueError("App name is required to use transitions")

        self._ctx = zmq.Context()
        self._in_stream = None
        self._sent = 0
        self._out_socket = None
        if setup_input:
            self.setup_input()
        if setup_output:
            self.setup_output()

        self._cb_app_heartbeat = None
        self._periodic_callbacks = {}

        use_redis = True
        if 'redis' in config:
            use_redis = config['redis'].get('enabled', True)
        if not use_redis:
            self._red = None
            self._red_sub = None
        else:
            self._red = ReconnectingRedis(self.verbose)
            self._red_sub = ReconnectingRedis(self.verbose, 'pubsub')
            self._setup_redis(sub_channels)

    def setup_input(self, cfg='input_stream', topic=INPUT_STREAM, bind=False):
        """
        Configure a ZMQ PUB socket for the input stream.
        """
        if self._in_stream:
            # Already configured the input stream, nothing to do.
            return

        sock_address = self.config[cfg]['socket']
        in_socket = self._ctx.socket(zmq.SUB)
        in_socket.setsockopt(zmq.SUBSCRIBE, topic)
        if bind:
            in_socket.bind(sock_address)
        else:
            in_socket.connect(sock_address)
        self._in_stream = zmqstream.ZMQStream(in_socket)

        callback = getattr(self, '_input_callback_%s' % cfg, None)
        if callback is None:
            raise Exception('Implementation not available for %s configuration' % cfg)
        self._in_stream.on_recv(callback, copy=False)
        if self.verbose:
            print("SUB socket %s to %s, topic %s" % (
                'bound' if bind else 'connected', sock_address, topic))

    def set_input_callback(self, function):
        """
        Define a callback to be invoked on messages received through
        the socket configured with setup_input.
        """
        self._input_callback = function

    def _input_callback_output_stream(self, msg):
        if not self._input_callback:
            return

        if len(msg) != 3:
            raise TypeError('expected output message of size %d, got %d' % (3, len(msg)))

        # topic = msg[0]  # unused.
        frame_num = struct.unpack('i', msg[1])[0]
        binimage_frame = msg[2]

        bin_image = numpy.frombuffer(binimage_frame.bytes, dtype=self._bin_dtype)
        bin_image = bin_image.reshape(self._bin_shape)

        self._input_callback(app=self, frame_num=frame_num, bin_image=bin_image)

    def _input_callback_input_transition_stream(self, msg):
        if not self._input_callback:
            return

        if len(msg) != 4:
            raise TypeError('expected transition message of size %d, got %d' % (4, len(msg)))

        # topic = msg[0]  # unused.
        app_name = str(msg[1])[:-1]
        frame_num = struct.unpack('i', msg[2])[0]
        binimage_frame = msg[3]

        bin_image = numpy.frombuffer(binimage_frame.bytes, dtype=self._bin_dtype)
        bin_image = bin_image.reshape(self._bin_shape)

        self._input_callback(
                app=self, frame_from=app_name, frame_num=frame_num,
                bin_image=bin_image)

    def _input_callback_input_stream(self, msg):
        if not self._input_callback:
            return

        if len(msg) != 4:
            raise TypeError('expected input message of size %d, got %d' % (4, len(msg)))

        # topic = msg[0]  # unused.
        frame_num = struct.unpack('i', msg[1])[0]
        depth_frame = msg[2]
        bgr_frame = msg[3]

        depth = numpy.frombuffer(depth_frame.bytes, dtype=self._depth_dtype)
        depth = depth.reshape(self._depth_shape)

        bgr = numpy.frombuffer(bgr_frame.bytes, dtype=self._bgr_dtype)
        bgr = bgr.reshape(self._bgr_shape)

        self._input_callback(app=self, frame_num=frame_num, depth=depth, bgr=bgr)

    def setup_output(self, cfg='output_stream', bind=None):
        """
        Configure a ZMQ PUB socket for the output stream.
        """
        if self._out_socket:
            return

        sock_address = self.config[cfg]['socket']
        self._out_socket = self._ctx.socket(zmq.PUB)
        if bind is None:
            bind = not self._out_transition
        if bind:
            self._out_socket.bind(sock_address)
        else:
            self._out_socket.connect(sock_address)
        if self.verbose:
            print("PUB socket %s to %s" % ('bound' if bind else 'connected', sock_address))

    def send_output(self, result, topic=OUTPUT_STREAM):
        """
        Publish result to the specific topic using the output socket
        configured by setup_output.

        An integer is returned. This number indicates the number of frames
        sent so far, i.e. the number of send_output invocations, starting
        from 1.
        """
        if not self._out_socket:
            raise Exception("output stream not configured")

        self._sent += 1
        if self._out_transition:
            # When (potentially) using transitions, also send the app name.
            data = [b'%s\x00' % topic, b'%s\x00' % self.name,
                    struct.pack('i', self._sent), result.tobytes()]
        else:
            data = [b'%s\x00' % topic,
                    struct.pack('i', self._sent), result.tobytes()]
        self._out_socket.send_multipart(data, copy=False)
        return self._sent

    def notify(self, channel, data):
        """Send json.dumps(data) to a channel using redis pubsub."""
        if not self._red:
            raise Exception("redis not enabled")
        return self._red.publish(channel, json.dumps(data))

    def add_periodic_callback(self, function, float_sec):
        """
        Schedule function to be called once each n seconds. The callback
        will receive this instance as its sole argument.

        The returned key can be used with stop_periodic_callback to stop
        the scheduling.
        """
        cb = ioloop.PeriodicCallback(
                lambda: function(self),
                float_sec * 1000)  # convert to ms
        key = id(cb)
        self._periodic_callbacks[key] = cb
        return key

    def stop_periodic_callback(self, key):
        """
        Stop a periodic callback created with add_periodic_callback.
        """
        cb = self._periodic_callbacks.pop(key)
        cb.stop()

    def run(self):
        """
        Start the registered callbacks and the event loop.
        If a name was specified, the app will be registered on
        redis if it's enabled.
        """
        if self.name and self._red is not None:
            self._cb_app_heartbeat = ioloop.PeriodicCallback(
                    self._app_heartbeat, 1000)
            self._cb_app_heartbeat.start()
        for cb in self._periodic_callbacks.values():
            cb.start()
        ioloop.IOLoop.instance().start()

    def cleanup(self):
        """
        Call this before quitting to stop registered callbacks and
        unregister the app from redis.
        """
        for cb in self._periodic_callbacks.values():
            cb.stop()
        if self._cb_app_heartbeat:
            self._cb_app_heartbeat.stop()
        if self.name and self._red is not None:
            # Unregister app from redis.
            self._red.hdel(REDIS_KEYS.APPS, self.name)

    def _app_heartbeat(self):
        # Update register on redis to indicate that the app is running well.
        self.config['timestamp'] = time.time()
        if self._red.is_connected():
            self._red.hset(REDIS_KEYS.APPS, self.name, json.dumps(self.config))

    def _setup_redis(self, channels):
        cfg = {'host': 'localhost', 'port': 6379, 'callback': self._on_redis_connect}
        if 'redis' in self.config:
            if 'host' in self.config['redis']:
                cfg['host'] = self.config['redis']['host']
            if 'port' in self.config['redis']:
                cfg['port'] = self.config['redis']['port']

        try:
            # Keep one redis connection for regular commands.
            self._red.connect(**cfg)
            # And another redis connection for pubsub.
            cb = partial(cfg.pop('callback'), sub_channels=channels)
            self._red_sub.connect(callback=cb, **cfg)
        except socket.error as err:
            if err.errno == errno.ECONNREFUSED:
                raise IOError("Could not connect to redis at {host}:{port}".format(**cfg))
            raise

    def _on_redis_message(self, msg):
        if msg is None:
            return
        msg_type, msg_channel, content = msg
        if msg_type != 'message':
            return

        data = json.loads(content)
        if msg_channel.startswith(REDIS_KEYS.APP_CHANNEL):
            # Update app settings.
            _update_settings(self.config['settings'], data)
            self._app_heartbeat()

        # XXX handle other kinds of updates (e.g. live stream settings).

    def _on_redis_connect(self, sub_channels=None):
        if 'redis' in self.config:
            db = self.config['redis'].get('db')
            if db:
                self._red.select(db)
            pwd = self.config['redis'].get('auth')
            if pwd:
                self._red.auth(pwd)

        if sub_channels:
            self._red_sub.subscribe(sub_channels, self._on_redis_message)


def _update_settings(settings, new):
    # Restrict key updates to those that already exist and
    # enforce the values to be of same type.
    def update(orig_data, new_data):
        for key, new_value in new_data.items():
            if key in orig_data:
                if isinstance(new_value, collections.Mapping):
                    # Recurse on nested settings.
                    res = update(orig_data[key], new_value)
                    orig_data[key] = res
                else:
                    orig_data[key] = type(orig_data[key])(new_value)
        return orig_data
    update(settings, new)