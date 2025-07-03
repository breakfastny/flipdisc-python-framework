import json
import struct
import logging
import logging.config
import asyncio
import numpy
import collections
import time
from redis import RedisError

import zmq
import zmq.asyncio

from .red import ReconnectingRedis
from .common import REDIS_KEYS, INPUT_STREAM, HDMI_INPUT_STREAM, OUTPUT_STREAM
from .common import ScheduledFunction

from typing import Any, Callable, Dict, List, Optional, Union

__all__ = ["Application"]


class Application(object):
    def __init__(
        self,
        name: str,
        config: Union[Dict[Any, Any], str],
        setup_input: bool = True,
        setup_output: bool = True,
        setup_hdmi_input: bool = True,
        verbose: bool = False,
    ) -> None:
        """
        An user app instance.

        * name should be a string. It will be used to store app data on redis
          and to identify the app through the http server.
          Accessible through instance.name

        * config can be either a string or a dict, if it's a string
          json.load(open(config)) will be used.
          + "logging" will be passed to logging.config.dictConfig(..)
          + If "output_stream", "input_stream" or "hdmi_stream" keys are present,
          they must specify at least a "width" and "height" subkeys.
          + If a "redis" key is present it will be used to configure the redis
          client.
          + The "settings" key must be used for holding settings specific
          to the app that can be updated while it's running.
          The app is free to use any other keys.
          Accessible through instance.config

        * verbose should be a boolean.
          Accessible through instance.verbose

        * if setup_input is True a SUB socket for the input stream will be
          configured for the topic framework.INPUT_STREAM using
          config["input_stream"]. The same applies for setup_hdmi_input
          with topic frame.HDMI_INPUT_STREAM and config["hdmi_stream"].

        * if setup_output is True a PUB socket for the output stream will be
          configured using config["output_stream"]
        """

        def load_config(config: Union[Dict[Any, Any], str]) -> Dict[Any, Any]:
            loaded_config: Dict[Any, Any]
            if not isinstance(config, dict):
                # Load config from json file.
                loaded_config = json.load(open(config))
            else:
                loaded_config = config
            if "logging" in loaded_config:
                logging.config.dictConfig(loaded_config["logging"])
            else:
                logging.basicConfig(
                    level=logging.DEBUG if verbose else logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(process)d %(message)s",
                )
            return loaded_config

        self.name = str.encode(name)
        self.verbose = verbose
        self.config: Dict[Any, Any] = load_config(config)
        self._log = logging.getLogger(__name__)

        self._loop = asyncio.get_event_loop()
        self._cb_app_heartbeat = None
        self._scheduled_functions = {}

        # List of redis channels to subscribe.
        self._sub_channels = []

        self._input_callback = {}
        self._loop = asyncio.get_event_loop()

        if "input_stream" in self.config:
            input_width = self.config["input_stream"]["width"]
            input_height = self.config["input_stream"]["height"]
            self._bgr_shape = (input_height, input_width, 3)
            self._depth_shape = (input_height, input_width)
            self._sub_channels.append(REDIS_KEYS.SYS_INPUT_CHANNEL.value)
        else:
            setup_input = False
            self._bgr_shape = None
            self._depth_shape = None

        if "hdmi_stream" in self.config:
            hdmi_width = self.config["hdmi_stream"]["width"]
            hdmi_height = self.config["hdmi_stream"]["height"]
            self._hdmi_shape = (hdmi_height, hdmi_width, 3)
            self._sub_channels.append(REDIS_KEYS.SYS_HDMI_CHANNEL.value)
        else:
            setup_hdmi_input = False
            self._hdmi_shape = None

        self._bgr_dtype = "uint8"
        self._depth_dtype = "uint16"
        self._hdmi_dtype = "uint8"

        if "output_stream" in self.config:
            output_width = self.config["output_stream"]["width"]
            output_height = self.config["output_stream"]["height"]
            self._bin_shape = (output_height, output_width)
            self._out_transition = self.config["output_stream"].get("transition", False)
            self._out_preview = self.config["output_stream"].get("preview", False)
            subtopic = self.config["output_stream"].get("subtopic")
            self._sub_channels.append(REDIS_KEYS.SYS_OUTPUT_CHANNEL.value)
        else:
            setup_output = False
            subtopic = None
            self._bin_shape = None
            self._out_transition = False
            self._out_preview = False
        self._bin_dtype = "uint8"
        if self._out_transition and not self.name:
            raise ValueError("App name is required to use transitions")

        self._app_rkey: Optional[bytes] = None
        if self.name:
            self._app_rkey = self.name
            if subtopic is not None:
                self._app_rkey += b":" + str.encode(subtopic)
            self._sub_channels.append(REDIS_KEYS.APP_CHANNEL.value + self._app_rkey)

        self._ctx = zmq.asyncio.Context()
        self._in_stream = {}
        self._sent: int = 0
        self._out_socket = None
        self._out_topic = None
        if setup_input:
            self.setup_input()
        if setup_hdmi_input:
            self.setup_input("hdmi_stream", HDMI_INPUT_STREAM)
        if setup_output:
            self.setup_output()

    async def setup_redis(self):
        self._cb_app_heartbeat = None
        self._redis_sub_callback = None
        self._red: Optional[ReconnectingRedis] = None
        self._red_sub: Optional[ReconnectingRedis] = None
        self._pubsub = None

        config = self.config.get("redis", {})

        if config.get("enabled", True) == False:
            return

        host = config.get("host", "localhost")
        port = config.get("port", 6379)
        db = config.get("db", None)
        pwd = config.get("auth", None)
        channels = self._sub_channels

        # Keep one redis connection for regular commands.
        self._red = ReconnectingRedis(
            suffix=None,
            host=host,
            port=port,
            db=db,
            password=pwd,
            retry_on_timeout=True,
        )

        # And another redis connection for pubsub.
        self._red_sub = ReconnectingRedis(
            suffix=None,
            host=host,
            port=port,
            db=db,
            password=pwd,
            retry_on_timeout=True,
        )

        if channels:
            self._loop.create_task(
                self._red_sub.subscribe(self._on_redis_message, *channels)
            )

    def setup_input(
        self,
        cfg: str = "input_stream",
        topic: str = INPUT_STREAM,
        bind: bool = False,
        watermark: int = 0,
    ) -> None:
        """
        Configure a ZMQ PUB socket for the input stream.
        """
        if cfg in self._in_stream:
            # Already configured the input stream, nothing to do.
            return

        sock_address = self.config[cfg]["socket"]
        in_socket = self._ctx.socket(zmq.SUB)

        in_socket.setsockopt_string(zmq.SUBSCRIBE, topic)
        if watermark > 0:
            in_socket.set_hwm(watermark)

        if bind:
            in_socket.bind(sock_address)
        else:
            in_socket.connect(sock_address)

        # TODO(wrigby): This is quite hacky - we shouldn't be doing this
        callback = getattr(self, "_input_callback_%s" % cfg, None)
        if callback is None:
            raise Exception("Implementation not available for %s configuration" % cfg)

        async def receive_stream(socket: zmq.asyncio.Socket, callback: Callable):
            while True:
                try:
                    msg = await socket.recv_multipart()
                    callback(msg)
                except Exception as e:
                    self._log.error("Error waiting for ZMQ stream message")
                    self._log.exception(e)

        self._in_stream[cfg] = self._loop.create_task(
            receive_stream(in_socket, callback)
        )

        self._log.debug(
            "SUB socket %s to %s, topic %s",
            "bound" if bind else "connected",
            sock_address,
            topic,
        )

    def set_input_callback(
        self, function: Callable, stream: str = "input_stream"
    ) -> None:
        """
        Define a callback to be invoked on messages received through
        the socket configured with setup_input.
        """
        self._input_callback[stream] = function

    def _input_callback_output_stream(self, msg: List[bytes]) -> None:
        cb = self._input_callback.get("output_stream")

        if cb is None or msg is None:
            return

        if len(msg) != 3:
            self._log.error("expected output message of size %d, got %d", 3, len(msg))
            return

        topic = msg[0]
        subtopic: Optional[bytes] = topic.split(b":", 1)[1].rstrip(b"\x00") if b":" in topic else None
        frame_num = struct.unpack("i", msg[1])[0]
        binimage_frame = msg[2]

        bin_image = numpy.frombuffer(binimage_frame, dtype=self._bin_dtype)
        try:
            bin_image = bin_image.reshape(self._bin_shape)
        except ValueError:
            self._log.exception("ignoring bad frame")
            return

        cb(app=self, subtopic=subtopic, frame_num=frame_num, bin_image=bin_image)

    # Preview stream is processed the same way as the output stream.
    _input_callback_preview_stream = _input_callback_output_stream

    def _input_callback_input_transition_stream(self, msg: List[bytes]):
        cb = self._input_callback.get("transition_stream")
        if cb is None:
            return

        if len(msg) != 4:
            self._log.error(
                "expected transition message of size %d, got %d", 4, len(msg)
            )
            return

        # topic = msg[0]  # unused.
        app_name = str(msg[1])[:-1]
        frame_num = struct.unpack("i", msg[2])[0]
        binimage_frame = msg[3]

        bin_image = numpy.frombuffer(binimage_frame, dtype=self._bin_dtype)
        try:
            bin_image = bin_image.reshape(self._bin_shape)
        except ValueError:
            self._log.exception("ignoring bad frame")
            return

        cb(app=self, frame_from=app_name, frame_num=frame_num, bin_image=bin_image)

    def _input_callback_input_stream(self, msg: List[bytes]):
        cb = self._input_callback.get("input_stream")
        if cb is None:
            return

        if len(msg) != 4:
            self._log.error("expected input message of size %d, got %d", 4, len(msg))
            return

        # topic = msg[0]  # unused.
        frame_num = struct.unpack("i", msg[1])[0]
        depth_frame = msg[2]
        bgr_frame = msg[3]

        depth = numpy.frombuffer(depth_frame, dtype=self._depth_dtype)
        bgr = numpy.frombuffer(bgr_frame, dtype=self._bgr_dtype)
        try:
            depth = depth.reshape(self._depth_shape)
            bgr = bgr.reshape(self._bgr_shape)
        except ValueError:
            self._log.exception("ignoring bad frame")
            return

        cb(app=self, frame_num=frame_num, depth=depth, bgr=bgr)

    def _input_callback_hdmi_stream(self, msg: List[bytes]):
        cb = self._input_callback.get("hdmi_stream")
        if cb is None:
            return

        if len(msg) != 3:
            self._log.error("expected hdmi message of size %d, got %d", 3, len(msg))
            return

        frame_num = struct.unpack("i", msg[1])[0]
        bgr_frame = msg[2]

        bgr = numpy.frombuffer(bgr_frame, dtype=self._hdmi_dtype)
        try:
            bgr = bgr.reshape(self._hdmi_shape)
        except ValueError:
            self._log.exception("ignoring bad frame")
            return

        cb(app=self, frame_num=frame_num, bgr=bgr)

    def setup_output(
        self, cfg: str = "output_stream", bind: Optional[bool] = None
    ) -> None:
        """
        Configure a ZMQ PUB socket for the output stream.
        """
        if self._out_socket:
            return

        sock_address = self.config[cfg]["socket"]
        subtopic: str = self.config[cfg].get("subtopic")
        subtopic = ":%s" % subtopic if subtopic else ""

        self._out_socket = self._ctx.socket(zmq.PUB)
        self._out_topic = bytes(OUTPUT_STREAM + subtopic, encoding="utf8")
        if bind is None:
            bind = (not self._out_transition) and (not self._out_preview)
        if bind:
            self._out_socket.bind(sock_address)
        else:
            self._out_socket.connect(sock_address)

        self._log.debug(
            "PUB socket %s to %s, topic %s",
            "bound" if bind else "connected",
            sock_address,
            self._out_topic,
        )

    async def send_output(
        self, result: numpy.ndarray, topic: Optional[bytes] = None
    ) -> int:
        """
        Publish result using the output socket configured by setup_output.

        An integer is returned. This number indicates the number of frames
        sent so far, i.e. the number of send_output invocations, starting
        from 1, wrapping around to 0 at UINT32_MAX.
        """
        if not self._out_socket:
            raise Exception("output stream not configured")

        # Wrap the sent count to uint32
        self._sent = (self._sent + 1) & 0xFFFFFFFF
        topic = self._out_topic if topic is None else bytes(topic)
        if self._out_transition:
            # When (potentially) using transitions, also send the app name.
            data = [
                b"%s\x00" % topic,
                b"%s\x00" % self.name,
                struct.pack("I", self._sent),
                result.tobytes(),
            ]
        else:
            data = [b"%s\x00" % topic, struct.pack("I", self._sent), result.tobytes()]
        await self._out_socket.send_multipart(data, copy=False)
        return self._sent

    async def notify(self, channel, data):
        """Send json.dumps(data) to a channel using redis pubsub."""
        if not self._red:
            raise Exception("redis not enabled")
        self._log.debug("Redis outgoing, channel: %s, data: %s", channel, data)
        return await self._red.pubsub.publish(channel, json.dumps(data))

    def set_redis_callback(self, function: Callable):
        """
        Define a callback to be invoked on messages received through
        the redis pubsub.
        """
        self._redis_sub_callback = function

    def add_periodic_callback(
        self, function: Callable, float_sec: float, start: bool = False
    ) -> int:
        """
        Schedule function to be called once each n seconds. The callback
        will receive this instance as its sole argument.

        The returned key can be used with stop_periodic_callback to stop
        the scheduling.
        """
        periodic = ScheduledFunction(
           float_sec, function, [self], periodic=True, loop=self._loop
        )
        key = id(periodic)
        self._scheduled_functions[key] = periodic
        if start:
            periodic.start()
        return key

    def stop_periodic_callback(self, key: str):
        """
        Stop a periodic callback created with add_periodic_callback.
        """
        periodic = self._scheduled_functions.pop(key)
        periodic.stop()

    async def call_later(self, float_sec: float, function: Callable):
        """
        Schedule function to be called after float_sec seconds have passed.

        The returned handle can be used with cancel_call_later to cancel the
        future call.
        """
        func = ScheduledFunction(float_sec, function, [self], False, self._loop)
        func.start()
        return func

    def cancel_call_later(self, handle):
        """
        Stop a scheduled call_later function from running.
        """
        handle.stop()

    def stop_ioloop(self):
        """
        Stop the event loop.
        Note: call the cleanup function after this one if the app is quitting.
        """
        self._loop.stop()

    async def run(self):
        """
        Start the registered callbacks and the event loop.
        If a name was specified, the app will be registered on
        redis if it's enabled.
        """
        if self.name and self._red is not None:
            key = self.add_periodic_callback(self._app_heartbeat, 1, True)
            self._cb_app_heartbeat = self._scheduled_functions[key]
        for pf in self._scheduled_functions.values():
            if not pf.started:
                pf.start()
        tasks = [x.get_task() for x in self._scheduled_functions.values()]
        await asyncio.gather(*tasks)

    async def cleanup(self) -> None:
        """
        Call this before quitting to stop registered callbacks and
        unregister the app from redis.
        """
        for pf in self._scheduled_functions.values():
            pf.stop()
        for t in self._in_stream.values():
            t.cancel()
        if self._cb_app_heartbeat:
            self._cb_app_heartbeat.stop()
        if self.name and self._red is not None:
            # Unregister app from redis.
            await self._red.hdel(REDIS_KEYS.APPS.value, self._app_rkey) # type: ignore
            if self._red is not None:
                await self._red.close()
            if self._red_sub is not None:
                await self._red_sub.close()

    async def _app_heartbeat(self, app: "Application") -> None:
        # Update register on redis to indicate that the app is running well.
        self.config["timestamp"] = time.time()
        try:
            await self._red.hset( # type: ignore
                REDIS_KEYS.APPS.value, self._app_rkey, json.dumps(self.config) # type: ignore
            )
        except:
            self._log.error("No redis configuration was found")

    def _on_redis_message(self, msg):
        if msg is None:
            return
        msg_type = msg["type"]
        msg_channel = msg["channel"]
        content = msg["data"]

        self._log.debug(
            "Redis incoming, type: %s, channel: %s, msg: %s",
            msg_type,
            msg_channel,
            content,
        )

        if msg_type != "message":
            return

        data = json.loads(content)
        if msg_channel.startswith(REDIS_KEYS.APP_CHANNEL.value.decode()):
            # Update app settings.
            _update_settings(self.config["settings"], data)
            await self._app_heartbeat()
        elif msg_channel == REDIS_KEYS.SYS_INPUT_CHANNEL.value.decode():
            # Input stream update.
            _update_settings(self.config["input_stream"], data)
            input_height = self.config["input_stream"]["height"]
            input_width = self.config["input_stream"]["width"]
            self._bgr_shape = (input_height, input_width, 3)
            self._depth_shape = (input_height, input_width)
        elif msg_channel == REDIS_KEYS.SYS_OUTPUT_CHANNEL.value.decode():
            # Output stream update.
            _update_settings(self.config["output_stream"], data)
            self._bin_shape = (
                self.config["output_stream"]["height"],
                self.config["output_stream"]["width"],
            )

        if self._redis_sub_callback:
            self._log.debug("Redis sub callback")
            self._redis_sub_callback(app=self, channel=msg_channel, update=data)


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
