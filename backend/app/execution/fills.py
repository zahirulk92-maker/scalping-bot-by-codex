"""Deterministic, conservative paper fill and PnL formulas."""

from decimal import Decimal

from app.strategy.models import SignalDirection


def entry_fill(market_price: Decimal, direction: SignalDirection, bps: Decimal) -> Decimal:
    multiplier = Decimal(1) + bps / Decimal(10_000) if direction == SignalDirection.LONG else Decimal(1) - bps / Decimal(10_000)
    return market_price * multiplier


def exit_fill(trigger_price: Decimal, direction: SignalDirection, bps: Decimal) -> Decimal:
    """Always adverse: long sells lower, short buys higher."""
    multiplier = Decimal(1) - bps / Decimal(10_000) if direction == SignalDirection.LONG else Decimal(1) + bps / Decimal(10_000)
    return trigger_price * multiplier


def fee(notional: Decimal, bps: Decimal) -> Decimal:
    return notional * bps / Decimal(10_000)


def gross_pnl(entry: Decimal, exit_price: Decimal, quantity: Decimal, direction: SignalDirection) -> Decimal:
    return (exit_price - entry) * quantity if direction == SignalDirection.LONG else (entry - exit_price) * quantity
