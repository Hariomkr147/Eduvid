"""Per-engine fair scheduler.

Pipeline requests go first, but while external requests are waiting, every 3rd slot goes to an
external one. Externals beyond max_waiting are refused with 429 (pipeline calls are never refused:
their volume is bounded by our own workers).
"""
import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .errors import ApiError

T = TypeVar("T")
EXTERNAL_EVERY = 3  # 1 slot in 3 for externals while any are waiting


class EngineScheduler:
    def __init__(self, engine: str, concurrency: int = 1, max_waiting: int = 32):
        self.engine = engine
        self.concurrency = concurrency
        self.max_waiting = max_waiting
        self.running = 0
        self._pipe: deque[asyncio.Future] = deque()
        self._ext: deque[asyncio.Future] = deque()
        self._pipe_streak = 0  # pipeline grants in a row while an external was waiting

    @property
    def waiting(self) -> int:
        return len(self._pipe) + len(self._ext)

    def stats(self) -> dict:
        return {"running": self.running, "waiting_pipeline": len(self._pipe), "waiting_external": len(self._ext)}

    def _pick(self) -> asyncio.Future | None:
        if self._ext and (not self._pipe or self._pipe_streak >= EXTERNAL_EVERY - 1):
            self._pipe_streak = 0
            return self._ext.popleft()
        if self._pipe:
            if self._ext:
                self._pipe_streak += 1
            return self._pipe.popleft()
        return None

    def _dispatch(self) -> None:
        while self.running < self.concurrency:
            fut = self._pick()
            if fut is None:
                return
            if fut.done():  # cancelled while waiting
                continue
            self.running += 1
            fut.set_result(None)

    async def submit(self, call: Callable[[], Awaitable[T]], pipeline: bool) -> T:
        if not pipeline and len(self._ext) >= self.max_waiting:
            raise ApiError(429, "engine queue full", headers={"Retry-After": "10"}, engine=self.engine)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        (self._pipe if pipeline else self._ext).append(fut)
        self._dispatch()
        try:
            await fut
        except asyncio.CancelledError:
            if fut.done() and not fut.cancelled():
                self.running -= 1  # slot was granted, then we were cancelled
                self._dispatch()
            else:
                q = self._pipe if pipeline else self._ext
                try:
                    q.remove(fut)
                except ValueError:
                    pass
            raise
        try:
            return await call()
        finally:
            self.running -= 1
            self._dispatch()
