"""ATR-derived, closed-candle planning levels without execution behavior."""

from decimal import Decimal

from app.strategy.models import SignalDirection


def plan_levels(direction: SignalDirection, entry: Decimal, atr: Decimal, stop_multiplier: Decimal, target_rr: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    if direction not in (SignalDirection.LONG, SignalDirection.SHORT):
        raise ValueError("only long and short directions can have plan levels")
    if entry <= 0 or atr <= 0 or stop_multiplier <= 0 or target_rr <= 0:
        raise ValueError("entry, ATR, stop multiplier, and target RR must be positive")
    stop_distance = atr * stop_multiplier
    if direction == SignalDirection.LONG:
        return entry - stop_distance, entry + stop_distance * target_rr, stop_distance
    return entry + stop_distance, entry - stop_distance * target_rr, stop_distance
