"""Pure performance metric calculations with safe zero-trade behavior."""

from decimal import Decimal

from app.backtest.models import BacktestTrade, EquityPoint, PerformanceSlice


def performance_slice(trades: list[BacktestTrade]) -> PerformanceSlice:
    wins = [trade for trade in trades if trade.net_pnl > 0]
    losses = [trade for trade in trades if trade.net_pnl < 0]
    gross_wins = sum((trade.net_pnl for trade in wins), Decimal(0))
    gross_losses = sum((trade.net_pnl for trade in losses), Decimal(0))
    rs = [trade.r_multiple for trade in trades if trade.r_multiple is not None]
    return PerformanceSlice(trades=len(trades), wins=len(wins), net_pnl=sum((trade.net_pnl for trade in trades), Decimal(0)), profit_factor=(gross_wins / abs(gross_losses) if gross_losses else None), average_r=(sum(rs, Decimal(0)) / len(rs) if rs else None))


def equity_point(timestamp, equity: Decimal, peak: Decimal) -> EquityPoint:
    drawdown = peak - equity
    return EquityPoint(timestamp=timestamp, equity=equity, drawdown_usdt=drawdown, drawdown_percent=(drawdown / peak * Decimal(100) if peak else Decimal(0)))
