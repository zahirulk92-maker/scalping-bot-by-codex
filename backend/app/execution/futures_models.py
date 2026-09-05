"""Immutable futures demo account, position, and trade records."""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

from app.strategy.models import SignalDirection
from app.execution.models import PositionStatus


class FuturesDemoAccount(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str
    wallet_balance: Decimal = Field(gt=0)
    available_balance: Decimal
    equity: Decimal
    unrealized_pnl: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)
    margin_balance: Decimal
    used_margin: Decimal
    free_margin: Decimal
    fees_paid: Decimal = Decimal(0)
    funding_paid: Decimal = Decimal(0)
    updated_at: datetime


class FuturesDemoPosition(BaseModel):
    model_config = ConfigDict(frozen=True)

    position_id: str
    symbol: str
    side: SignalDirection
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    leverage: int
    notional: Decimal
    initial_margin: Decimal
    maintenance_margin: Decimal
    liquidation_price: Decimal | None
    unrealized_pnl: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)
    stop_loss: Decimal
    take_profit: Decimal
    opened_at: datetime
    updated_at: datetime
    status: PositionStatus = PositionStatus.OPEN
    entry_fee_usdt: Decimal = Decimal(0)


class FuturesDemoFill(BaseModel):
    model_config = ConfigDict(frozen=True)

    fill_id: str
    position_id: str
    symbol: str
    side: SignalDirection
    quantity: Decimal
    price: Decimal
    fee_usdt: Decimal
    realized_pnl_usdt: Decimal = Decimal(0)
    is_maker: bool = False
    timestamp: datetime


class FundingEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    position_id: str
    symbol: str
    funding_rate: Decimal
    payment_usdt: Decimal
    timestamp: datetime


class LiquidationEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    position_id: str
    symbol: str
    mark_price: Decimal
    liquidation_price: Decimal
    maintenance_margin: Decimal
    margin_balance: Decimal
    timestamp: datetime
