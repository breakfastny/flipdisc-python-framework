import asyncio
import logging
import random
from redis import RedisError
import redis.asyncio

from .common import REDIS_KEYS


class ReconnectingRedis(redis.asyncio.Redis):
    def __init__(self, suffix, host, port, db, password, retry_on_timeout):
        self._log = logging.getLogger(__name__)
        self._retry_delay = 1
        self._name = "redis%s" % ("-%s" % suffix if suffix else "")
        self._host = host
        self._port = port
        self._pool = redis.asyncio.ConnectionPool(
            host=host,
            port=port,
            db=db,
            password=password,
            retry_on_timeout=retry_on_timeout,
        )
        super().__init__(connection_pool=self._pool)
        self.psub = self.pubsub()

    async def subscribe(self, callback, *channels):
        while True:
            try:
                await self.psub.subscribe(*channels)
                self._retry_delay = 1
                self._log.debug("%s connected", self._name)

                while True:
                    # Type check complains about iterating over a Coroutine type, but this is how
                    # the documentation indicates one should listen for messages.
                    async for msg in self.psub.listen():  # type: ignore
                        callback(msg)
                    await asyncio.sleep(0.01)

            except Exception as err:
                self._log.error(
                    "%s failed to connect to %s:%s - %s",
                    self._name,
                    self._host,
                    self._port,
                    err,
                )

                await self.psub.reset()

                self._retry_delay *= 2
                self._retry_delay += random.random()
                self._retry_delay = min(self._retry_delay, 10)

            await asyncio.sleep(self._retry_delay)
