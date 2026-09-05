"""Exchange adapter contract."""

from collections.abc import Awaitable, Callable
from typing import Protocol

from app.market.models import Candle, FeedState

CandleHandler = Callable[[Candle], Awaitable[None]]
StateHandler = Callable[[FeedState], Awaitable[None]]


class MarketDataAdapter(Protocol):
    exchange_name: str
    state: FeedState

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def fetch_historical_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]: ...
