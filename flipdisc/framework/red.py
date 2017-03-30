import random

from toredis import Client as RedisClient

__all__ = ['ReconnectingRedis']


class ReconnectingRedis(RedisClient):

    def __init__(self, verbose, extra_name=None, *args, **kwargs):
        super(ReconnectingRedis, self).__init__(*args, **kwargs)
        self._retry = 1
        self._name = 'redis%s' % ('-%s' % extra_name if extra_name else '')
        self._verbose = verbose

    def connect(self, host, port, callback=None):
        self.host = host
        self.port = port
        self.callback = callback
        self._reconnect()

    def on_disconnect(self):
        if self._verbose:
            print('%s not connected, retrying in %s' % (self._name, self._retry))
        self._io_loop.call_later(self._retry, self._reconnect)

    def _reconnect(self):
        try:
            super(ReconnectingRedis, self).connect(self.host, self.port, self.callback)
            self._retry = 1
        except Exception as err:
            self._retry *= 2
            self._retry += random.random()
            if self._retry > 10:
                self._retry = 1
            if self._verbose:
                print('%s failed to connect: %s' % (self._name, err))
        else:
            if self._verbose and self.is_connected():
                print('%s connected' % self._name)
