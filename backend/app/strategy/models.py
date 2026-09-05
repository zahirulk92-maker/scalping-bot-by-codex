"""Immutable strategy signal models with no order or execution fields."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SignalDirection(StrEnum):
    LONG = "long"
    SHORT = "short"
    NO_TRADE = "no_trade"


class SignalContext(BaseModel):
    """The exact closed-candle indicator values evaluated by the strategy."""

    model_config = ConfigDict(frozen=True)

    close: Decimal | None = None
    ema_9: Decimal | None = None
    ema_21: Decimal | None = None
    rsi_14: Decimal | None = None
    atr_14: Decimal | None = None
    vwap: Decimal | None = None
    volume: Decimal | None = None
    volume_ma_20: Decimal | None = None


class SignalSnapshot(BaseModel):
    """A deterministic strategy decision for one official indicator snapshot."""

    model_config = ConfigDict(frozen=True)

    signal_id: str = ""
    symbol: str
    timeframe: str
    direction: SignalDirection = SignalDirection.NO_TRADE
    score: int = Field(default=0, ge=0, le=100)
    confidence: float = Field(default=0, ge=0, le=1)
    reasons: tuple[str, ...] = ()
    candle_open_time: datetime | None = None
    candle_close_time: datetime | None = None
    generated_at: datetime | None = None
    is_actionable: bool = False
    context: SignalContext = Field(default_factory=SignalContext)
