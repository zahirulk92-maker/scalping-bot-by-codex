from decimal import Decimal


def simple_average(values: list[Decimal]) -> Decimal:
    return sum(values) / Decimal(len(values))


def next_ema(value: Decimal, previous: Decimal, period: int) -> Decimal:
    return (value - previous) * Decimal(2) / Decimal(period + 1) + previous
