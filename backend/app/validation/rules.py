"""Small deterministic calculations used by the validation engine."""

from datetime import UTC, datetime
from decimal import Decimal

from app.execution.models import ClosedPaperTrade


def trade_metrics(trades: list[ClosedPaperTrade], starting_balance: Decimal) -> dict[str, object]:
    wins = [item for item in trades if item.net_pnl_usdt > 0]
    losses = [item for item in trades if item.net_pnl_usdt < 0]
    gross_wins = sum((item.net_pnl_usdt for item in wins), Decimal(0))
    gross_losses = sum((item.net_pnl_usdt for item in losses), Decimal(0))
    r_values = [item.net_pnl_usdt / item.risk_amount_usdt for item in trades if item.risk_amount_usdt is not None and item.risk_amount_usdt > 0]
    equity = starting_balance
    peak = equity
    maximum_drawdown = Decimal(0)
    last_high_at: datetime | None = None
    for item in sorted(trades, key=lambda value: value.closed_at):
        equity += item.net_pnl_usdt
        if equity >= peak:
            peak = equity
            last_high_at = item.closed_at
        elif peak > 0:
            maximum_drawdown = max(maximum_drawdown, (peak - equity) / peak * Decimal(100))
    now = datetime.now(UTC)
    underwater_days = (now - last_high_at).total_seconds() / 86_400 if last_high_at and equity < peak else 0.0
    return {
        "trades": len(trades), "net_pnl": sum((item.net_pnl_usdt for item in trades), Decimal(0)), "fees": sum((item.fees_usdt for item in trades), Decimal(0)),
        "gross_profit": gross_wins, "wins": len(wins), "losses": len(losses), "win_rate": Decimal(len(wins)) / len(trades) if trades else None,
        "profit_factor": gross_wins / abs(gross_losses) if gross_losses else None,
        "expectancy_r": sum(r_values, Decimal(0)) / len(r_values) if r_values else None,
        "expectancy_net": sum((item.net_pnl_usdt for item in trades), Decimal(0)) / len(trades) if trades else None,
        "average_r": sum(r_values, Decimal(0)) / len(r_values) if r_values else None,
        "max_drawdown_percent": maximum_drawdown, "current_equity": equity, "peak_equity": peak,
        "current_drawdown_percent": (peak - equity) / peak * Decimal(100) if peak else Decimal(0), "underwater_days": underwater_days,
    }


def maximum_losing_streak(trades: list[ClosedPaperTrade]) -> int:
    streak = maximum = 0
    for item in sorted(trades, key=lambda value: value.closed_at):
        streak = streak + 1 if item.net_pnl_usdt < 0 else 0
        maximum = max(maximum, streak)
    return maximum
