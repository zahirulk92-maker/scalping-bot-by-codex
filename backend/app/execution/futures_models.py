"""Immutable futures demo account, position, and trade records for Phase 13."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
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


class FuturesSymbolRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    status: str
    price_tick_size: Decimal
    quantity_step_size: Decimal
    min_price: Decimal
    max_price: Decimal
    min_quantity: Decimal
    max_quantity: Decimal
    min_notional: Decimal
    market_min_quantity: Decimal
    market_max_quantity: Decimal
    updated_at: datetime


class DemoOrderIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent_id: str
    signal_id: Optional[str]
    trade_plan_id: Optional[str]
    symbol: str
    side: SignalDirection
    requested_quantity: Decimal
    requested_notional: Decimal
    created_at: datetime


class DemoOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str
    intent_id: str
    symbol: str
    side: SignalDirection
    order_type: str
    requested_quantity: Decimal
    filled_quantity: Decimal = Decimal(0)
    remaining_quantity: Decimal
    average_fill_price: Decimal = Decimal(0)
    status: str
    created_at: datetime
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
    order_id: str
    position_id: str
    symbol: str
    side: SignalDirection
    quantity: Decimal
    price: Decimal
    fee_usdt: Decimal
    spread_cost: Decimal = Decimal(0)
    slippage_cost: Decimal = Decimal(0)
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
    source: str
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
