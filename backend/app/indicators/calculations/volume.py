from decimal import Decimal


def volume_average(values: list[Decimal]) -> Decimal:
    return sum(values) / Decimal(len(values))
