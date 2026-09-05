"""Pure Decimal sizing functions for unrounded planning estimates."""

from decimal import Decimal


def size_from_risk(risk_amount: Decimal, stop_distance: Decimal, entry_price: Decimal) -> tuple[Decimal, Decimal]:
    if risk_amount <= 0 or stop_distance <= 0 or entry_price <= 0:
        raise ValueError("risk amount, stop distance, and entry price must be positive")
    quantity = risk_amount / stop_distance
    return quantity, quantity * entry_price


def cap_notional(notional: Decimal, entry_price: Decimal, stop_distance: Decimal, maximum: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Return capped notional, quantity, and actual risk after applying the cap."""
    if maximum <= 0 or entry_price <= 0 or stop_distance <= 0:
        raise ValueError("notional cap, entry price, and stop distance must be positive")
    capped_notional = min(notional, maximum)
    quantity = capped_notional / entry_price
    return capped_notional, quantity, quantity * stop_distance
