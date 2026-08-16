"""Strictly serial provider rate limiting."""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]


class SerialRateLimiter:
    """Allow one in-flight call and enforce spacing between call starts."""

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleeper = asyncio.sleep,
    ) -> None:
        if min_interval_seconds < 1.0:
            raise ValueError("Provider request interval must be at least one second")
        self.min_interval_seconds = min_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._semaphore = asyncio.Semaphore(1)
        self._last_started_at: float | None = None

    @asynccontextmanager
    async def slot(self, *, delay_seconds: float = 0.0) -> AsyncIterator[None]:
        """Reserve the only provider slot after required interval and retry delay."""

        async with self._semaphore:
            interval_delay = 0.0
            if self._last_started_at is not None:
                elapsed = self._clock() - self._last_started_at
                interval_delay = max(0.0, self.min_interval_seconds - elapsed)
            delay = max(0.0, delay_seconds, interval_delay)
            if delay:
                await self._sleep(delay)
            self._last_started_at = self._clock()
            yield
