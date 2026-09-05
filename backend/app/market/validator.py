"""Validation rules for normalized market data."""

from datetime import UTC

from app.core.exceptions import MarketDataError
from app.market.models import Candle


def validate_candle(candle: Candle, configured_symbols: set[str], timeframe: str) -> None:
    """Raise MarketDataError when a normalized candle is unsafe to store."""
    if candle.symbol not in configured_symbols:
        raise MarketDataError(f"unconfigured symbol: {candle.symbol}")
    if candle.timeframe != timeframe:
        raise MarketDataError(f"unexpected timeframe: {candle.timeframe}")
    if candle.open_time.tzinfo is None or candle.close_time.tzinfo is None:
        raise MarketDataError("candle timestamps must be timezone-aware UTC")
    if candle.open_time.utcoffset() != UTC.utcoffset(candle.open_time):
        raise MarketDataError("open_time must be UTC")
    if candle.close_time <= candle.open_time:
        raise MarketDataError("close_time must be after open_time")
    if any(value <= 0 for value in (candle.open, candle.high, candle.low, candle.close)):
        raise MarketDataError("OHLC prices must be positive")
    if candle.volume < 0:
        raise MarketDataError("volume must be non-negative")
    if candle.high < candle.low:
        raise MarketDataError("high must be greater than or equal to low")
    if candle.high < candle.open or candle.high < candle.close:
        raise MarketDataError("high must be greater than or equal to open and close")
    if candle.low > candle.open or candle.low > candle.close:
        raise MarketDataError("low must be less than or equal to open and close")
