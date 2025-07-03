import enum
import asyncio
from typing import Callable, Iterable, Optional


class REDIS_KEYS(enum.Enum):
    # hashtable used to store all active apps.
    # key is an app name and the value is a json.dumps of all its settings.
    APPS = b"fd:apps"
    # channel name used to send messages to specific apps.
    # When subscribing, use it as APP_CHANNEL + appname.
    APP_CHANNEL = b"fd:app:"
    # channel name used to send messages to all apps that use input settings.
    SYS_INPUT_CHANNEL = b"fd:system:input"
    # channel name used to send messages to all apps that use hdmi settings.
    SYS_HDMI_CHANNEL = b"fd:system:hdmi"
    # channel name used to send messages to all apps that use output settings.
    SYS_OUTPUT_CHANNEL = b"fd:system:output"


INPUT_STREAM = "IN_STREAM"
HDMI_INPUT_STREAM = "HDMI_STREAM"

OUTPUT_STREAM = "OUT_STREAM"


class ScheduledFunction:
    def __init__(
        self,
        delay: float,
        function: Callable,
        args: Iterable,
        periodic: bool = False,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.delay = delay
        self.function = function
        self.periodic = periodic
        self.started = False
        self._loop = loop if loop is not None else asyncio.get_event_loop()
        self._args = args
        self._task: Optional[asyncio.Task] = None

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
        if self.started and self._task is not None:
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
