import random
import logging

from toredis import Client as RedisClient

__all__ = ['ReconnectingRedis']


class ReconnectingRedis(RedisClient):

    def __init__(self, suffix=None, *args, **kwargs):
        super(ReconnectingRedis, self).__init__(*args, **kwargs)
        self._log = logging.getLogger(__name__)
        self._retry = 1
        self._name = 'redis%s' % ('-%s' % suffix if suffix else '')

    def connect(self, host, port, callback=None):
        self.host = host
        self.port = port
        self.callback = callback
        self._reconnect()

    def on_disconnect(self):
        self._log.error('%s not connected, retrying in %s', self._name, self._retry)
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
            self._log.error('%s failed to connect to %s:%s - %s',
                    self._name, self.host, self.port, err)
        else:
            if self.is_connected():
                self._log.debug('%s connected', self._name)
