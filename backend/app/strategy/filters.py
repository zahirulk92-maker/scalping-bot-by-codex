"""Pure numeric guardrails shared by the deterministic strategy rules."""

from decimal import Decimal


def bps_distance(left: Decimal, right: Decimal) -> Decimal | None:
    """Absolute distance in basis points, or None when the reference is invalid."""
    if right <= 0:
        return None
    return abs(left - right) / right * Decimal(10_000)


def ratio(value: Decimal, baseline: Decimal) -> Decimal | None:
    if baseline <= 0:
        return None
    return value / baseline


def relative_bps(value: Decimal, reference: Decimal) -> Decimal | None:
    """A value expressed as basis points of a positive reference price."""
    if reference <= 0:
        return None
    return value / reference * Decimal(10_000)
