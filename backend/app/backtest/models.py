"""Immutable backtest requests, audit records, metrics, and results."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.execution.models import ExitReason
from app.strategy.models import SignalDirection


class BacktestRequest(BaseModel):
    symbols: list[str]
    timeframe: str = "1m"
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def validate_range(self):
        if not self.symbols:
            raise ValueError("at least one symbol is required")
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class EquityPoint(BaseModel):
    model_config = ConfigDict(frozen=True)
    timestamp: datetime
    equity: Decimal
    drawdown_usdt: Decimal
    drawdown_percent: Decimal


class BacktestTrade(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    direction: SignalDirection
    signal_time: datetime | None = None
    entry_time: datetime
    entry_price: Decimal
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    exit_time: datetime
    exit_price: Decimal
    exit_reason: ExitReason
    quantity: Decimal
    planned_risk_amount: Decimal | None = None
    gross_pnl: Decimal
    fees: Decimal
    net_pnl: Decimal
    r_multiple: Decimal | None = None
    signal_score: int = 0


class PerformanceSlice(BaseModel):
    trades: int = 0
    wins: int = 0
    net_pnl: Decimal = Decimal(0)
    profit_factor: Decimal | None = None
    average_r: Decimal | None = None


class BacktestResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_id: str
    symbols: tuple[str, ...]
    timeframe: str
    start_time: datetime
    end_time: datetime
    starting_balance: Decimal
    ending_balance: Decimal
    total_trades: int
    wins: int
    losses: int
    breakeven_trades: int
    gross_profit: Decimal
    gross_loss: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    total_fees: Decimal
    total_slippage_cost: Decimal
    win_rate: Decimal | None = None
    profit_factor: Decimal | None = None
    expectancy_per_trade: Decimal | None = None
    max_drawdown_usdt: Decimal = Decimal(0)
    max_drawdown_percent: Decimal = Decimal(0)
    largest_win: Decimal | None = None
    largest_loss: Decimal | None = None
    average_win: Decimal | None = None
    average_loss: Decimal | None = None
    average_r_multiple: Decimal | None = None
    return_percent: Decimal = Decimal(0)
    signal_counts: dict[str, int] = Field(default_factory=dict)
    approved_plans: int = 0
    rejected_plans: int = 0
    rejection_counts: dict[str, int] = Field(default_factory=dict)
    symbol_performance: dict[str, PerformanceSlice] = Field(default_factory=dict)
    direction_performance: dict[str, PerformanceSlice] = Field(default_factory=dict)
    config_snapshot: dict[str, object] = Field(default_factory=dict)
    trades: tuple[BacktestTrade, ...] = ()
    equity_curve: tuple[EquityPoint, ...] = ()
