"""Async-safe bounded in-memory storage for normalized candles."""

import asyncio
from collections import deque

from app.market.models import Candle


class MarketStore:
    def __init__(self, history_limit: int) -> None:
        self._history_limit = history_limit
        self._closed: dict[tuple[str, str], deque[Candle]] = {}
        self._current: dict[tuple[str, str], Candle] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(candle: Candle) -> tuple[str, str]:
        return (candle.symbol, candle.timeframe)

    async def upsert_candle(self, candle: Candle) -> bool:
        """Store a newer update; return False for duplicate/out-of-order input."""
        key = self._key(candle)
        async with self._lock:
            history = self._closed.setdefault(key, deque(maxlen=self._history_limit))
            latest_closed = history[-1] if history else None
            current = self._current.get(key)

            if candle.is_closed:
                if latest_closed and candle.open_time < latest_closed.open_time:
                    return False
                for index, existing in enumerate(history):
                    if existing.open_time == candle.open_time:
                        if existing == candle:
                            return False
                        history[index] = candle
                        self._current.pop(key, None)
                        return True
                history.append(candle)
                if current and current.open_time <= candle.open_time:
                    self._current.pop(key, None)
                return True

            if latest_closed and candle.open_time <= latest_closed.open_time:
                return False
            if current and candle.open_time < current.open_time:
                return False
            if current == candle:
                return False
            self._current[key] = candle
            return True

    async def get_latest_candle(self, symbol: str, timeframe: str) -> Candle | None:
        async with self._lock:
            key = (symbol, timeframe)
            return self._current.get(key) or (self._closed.get(key) or [None])[-1]

    async def get_current_candle(self, symbol: str, timeframe: str) -> Candle | None:
        async with self._lock:
            return self._current.get((symbol, timeframe))

    async def get_recent_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        async with self._lock:
            key = (symbol, timeframe)
            candles = list(self._closed.get(key, ()))
            current = self._current.get(key)
            if current:
                candles.append(current)
            return candles[-limit:]
