from decimal import Decimal


def true_range(high: Decimal, low: Decimal, previous_close: Decimal | None) -> Decimal:
    values = [high - low]
    if previous_close is not None:
        values.extend([abs(high - previous_close), abs(low - previous_close)])
    return max(values)
