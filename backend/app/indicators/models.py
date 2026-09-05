"""Normalized indicator snapshots independent of exchange payloads."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class IndicatorSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: str
    candle_open_time: datetime | None = None
    candle_close_time: datetime | None = None
    close: Decimal | None = None
    ema_9: Decimal | None = None
    ema_21: Decimal | None = None
    rsi_14: Decimal | None = None
    atr_14: Decimal | None = None
    vwap: Decimal | None = None
    volume: Decimal | None = None
    volume_ma_20: Decimal | None = None
    is_ready: bool = False
    calculated_at: datetime | None = None
