import enum
import asyncio
from typing import Callable, Iterable

class REDIS_KEYS(enum.Enum):
    # hashtable used to store all active apps.
    # key is an app name and the value is a json.dumps of all its settings.
    APPS: str = "fd:apps"
    # channel name used to send messages to specific apps.
    # When subscribing, use it as APP_CHANNEL + appname.
    APP_CHANNEL: str = "fd:app:"
    # channel name used to send messages to all apps that use input settings.
    SYS_INPUT_CHANNEL: str = "fd:system:input"
    # channel name used to send messages to all apps that use hdmi settings.
    SYS_HDMI_CHANNEL: str = "fd:system:hdmi"
    # channel name used to send messages to all apps that use output settings.
    SYS_OUTPUT_CHANNEL: str = "fd:system:output"

INPUT_STREAM = "IN_STREAM"
HDMI_INPUT_STREAM = "HDMI_STREAM"

OUTPUT_STREAM = "OUT_STREAM"


class ScheduledFunction:
    def __init__(self, function: Callable, args: Iterable, delay: float, periodic: bool=False, loop=asyncio.AbstractEventLoop):
        self.delay = delay
        self.function = function
        self.periodic = periodic
        self.started = False
        self._loop = loop
        self._args = args
        self._task = None

    def get_task(self):
        return self._task

    def start(self):
        if not self.started:
            self.started = True
            try:
                self._task = self._loop.create_task(self._run())
            except asyncio.CancelledError:
                pass

    def stop(self):
        if self.started:
            self.started = False
            self._task.cancel()

    async def _run(self):
        if self.periodic == True:
            while True:
                await asyncio.gather(
                    asyncio.sleep(self.delay),
                    self.function(*self._args),
                )
        else:
            self._loop.call_later(self.delay, self.function)
