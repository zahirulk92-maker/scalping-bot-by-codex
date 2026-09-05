from decimal import Decimal


def typical_price(high: Decimal, low: Decimal, close: Decimal) -> Decimal:
    return (high + low + close) / Decimal(3)
