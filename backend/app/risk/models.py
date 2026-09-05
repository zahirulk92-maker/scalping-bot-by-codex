"""Strongly typed account and planning models with no exchange-order fields."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.strategy.models import SignalDirection


class RiskAccountState(BaseModel):
    """Explicit simulated account state, replaceable by a future execution integration."""

    model_config = ConfigDict(frozen=True)

    current_equity: Decimal = Field(gt=0)
    realized_pnl_today: Decimal = Decimal(0)
    open_position_count: int = Field(default=0, ge=0)

    @property
    def daily_loss_used(self) -> Decimal:
        return max(-self.realized_pnl_today, Decimal(0))


class TradePlan(BaseModel):
    """Risk-approved or rejected plan; it is never an exchange order."""

    model_config = ConfigDict(frozen=True)

    plan_id: str = ""
    source_signal_id: str | None = None
    symbol: str
    timeframe: str
    direction: SignalDirection = SignalDirection.NO_TRADE
    signal_score: int = Field(default=0, ge=0, le=100)
    signal_confidence: float = Field(default=0, ge=0, le=1)
    entry_reference_price: Decimal | None = None
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    stop_distance: Decimal | None = None
    stop_distance_bps: Decimal | None = None
    planned_risk_amount_usdt: Decimal | None = None
    actual_risk_amount_usdt: Decimal | None = None
    risk_amount_usdt: Decimal | None = None
    position_notional_usdt: Decimal | None = None
    estimated_quantity: Decimal | None = None
    reward_amount_usdt: Decimal | None = None
    risk_reward_ratio: Decimal | None = None
    estimated_fees_usdt: Decimal | None = None
    estimated_slippage_usdt: Decimal | None = None
    net_reward_usdt: Decimal | None = None
    approved: bool = False
    rejection_reasons: tuple[str, ...] = ()
    generated_at: datetime | None = None
    source_candle_open_time: datetime | None = None
    source_candle_close_time: datetime | None = None
