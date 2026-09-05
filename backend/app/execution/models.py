"""Immutable paper account, position, and trade records."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.strategy.models import SignalDirection


class PositionStatus(StrEnum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    RECOVERY_PENDING = "recovery_pending"


class ExitReason(StrEnum):
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    SAFETY_CLOSE = "safety_close"
    MANUAL_TEST_CLOSE = "manual_test_close"


class PaperAccount(BaseModel):
    model_config = ConfigDict(frozen=True)

    starting_balance: Decimal = Field(gt=0)
    cash_balance: Decimal
    equity: Decimal
    realized_pnl: Decimal = Decimal(0)
    realized_pnl_today: Decimal = Decimal(0)
    gross_pnl: Decimal = Decimal(0)
    fees_paid: Decimal = Decimal(0)
    open_position_count: int = Field(default=0, ge=0)
    closed_trade_count: int = Field(default=0, ge=0)
    winning_trade_count: int = Field(default=0, ge=0)
    losing_trade_count: int = Field(default=0, ge=0)
    win_rate: Decimal = Decimal(0)
    statistics_day: date


class PaperPosition(BaseModel):
    model_config = ConfigDict(frozen=True)

    position_id: str
    plan_identity: str
    source_plan_id: str | None = None
    symbol: str
    timeframe: str
    direction: SignalDirection
    entry_reference_price: Decimal
    entry_fill_price: Decimal
    current_price: Decimal
    quantity: Decimal
    position_notional: Decimal
    stop_loss_price: Decimal
    take_profit_price: Decimal
    risk_amount_usdt: Decimal
    entry_fee_usdt: Decimal
    estimated_exit_fee_usdt: Decimal
    unrealized_gross_pnl: Decimal = Decimal(0)
    unrealized_net_pnl: Decimal = Decimal(0)
    opened_at: datetime
    source_signal_time: datetime | None = None
    source_candle_open_time: datetime
    source_candle_close_time: datetime
    last_processed_at: datetime | None = None
    status: PositionStatus = PositionStatus.OPEN


class ClosedPaperTrade(BaseModel):
    model_config = ConfigDict(frozen=True)

    trade_id: str
    position_id: str
    symbol: str
    direction: SignalDirection
    entry_fill_price: Decimal
    exit_fill_price: Decimal
    quantity: Decimal
    risk_amount_usdt: Decimal | None = None
    gross_pnl_usdt: Decimal
    fees_usdt: Decimal
    net_pnl_usdt: Decimal
    exit_reason: ExitReason
    opened_at: datetime
    closed_at: datetime
    source_signal_time: datetime | None = None
