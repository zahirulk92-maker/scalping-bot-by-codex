"""Small dependency-free operational controls for the PAPER platform."""

import asyncio
import time
from collections import defaultdict, deque


class RequestRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True


class HeavyJobGuard:
    def __init__(self, backtests: int, optimizations: int) -> None:
        self.backtests = asyncio.Semaphore(backtests)
        self.optimizations = asyncio.Semaphore(optimizations)

    @staticmethod
    def available(semaphore: asyncio.Semaphore) -> bool:
        return not semaphore.locked()
