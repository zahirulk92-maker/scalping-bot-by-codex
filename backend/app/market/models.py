"""Normalized, exchange-independent market data models."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class FeedState(StrEnum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"
    STALE = "stale"
    ERROR = "error"


class Candle(BaseModel):
    """A validated OHLCV candle; all timestamps are UTC."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool


class SymbolFeedStatus(BaseModel):
    status: FeedState
    last_update: datetime | None = None


class MarketFeedStatus(BaseModel):
    exchange: str
    status: FeedState
    timeframe: str
    symbols: dict[str, SymbolFeedStatus]
