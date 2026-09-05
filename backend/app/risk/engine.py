"""Idempotent, fail-closed trade-plan generation with no execution capability."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

from app.config import Settings
from app.market.models import MarketFeedStatus
from app.risk.guards import account_rejection_reasons, market_rejection_reasons, signal_rejection_reasons
from app.risk.models import RiskAccountState, TradePlan
from app.risk.sizing import cap_notional, size_from_risk
from app.risk.stops import plan_levels
from app.risk.store import RiskStore
from app.strategy.models import SignalSnapshot

logger = logging.getLogger(__name__)
PlanHandler = Callable[[TradePlan], Awaitable[None]]
MarketStatusProvider = Callable[[], MarketFeedStatus]
NowProvider = Callable[[], datetime]


class RiskEngine:
    """Transforms one actionable signal into at most one risk plan per source candle."""

    def __init__(self, settings: Settings, market_status_provider: MarketStatusProvider | None = None, on_plan: PlanHandler | None = None, store: RiskStore | None = None, now_provider: NowProvider | None = None) -> None:
        self.settings = settings
        self.store = store or RiskStore(settings)
        self._market_status_provider = market_status_provider
        self._on_plan = on_plan
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._last_open_time: dict[tuple[str, str], datetime] = {}
        self._lock = asyncio.Lock()
        logger.info("Risk engine initialized in plan-only mode; execution is disabled")

    def set_plan_handler(self, handler: PlanHandler) -> None:
        self._on_plan = handler

    async def process_signal(self, signal: SignalSnapshot) -> TradePlan | None:
        key = (signal.symbol, signal.timeframe)
        if signal.candle_open_time is None:
            return None
        async with self._lock:
            previous = self._last_open_time.get(key)
            if previous is not None and signal.candle_open_time <= previous:
                logger.debug("Ignored duplicate/out-of-order risk signal for %s", signal.symbol)
                return None
            plan = await self._build_plan(signal)
            self._last_open_time[key] = signal.candle_open_time
            await self.store.save(plan)
        if self._on_plan:
            await self._on_plan(plan)
        return plan

    async def _build_plan(self, signal: SignalSnapshot) -> TradePlan:
        now = self._now()
        reasons = signal_rejection_reasons(signal, self.settings, now)
        status = self._market_status_provider() if self._market_status_provider else None
        reasons.extend(market_rejection_reasons(signal.symbol, status))
        account = await self.store.account_state()
        base = self._base_plan(signal, now)
        if reasons:
            return base.model_copy(update={"rejection_reasons": tuple(reasons)})

        entry = signal.context.close
        atr = signal.context.atr_14
        assert entry is not None and atr is not None
        stop, take_profit, stop_distance = plan_levels(signal.direction, entry, atr, Decimal(str(self.settings.atr_stop_multiplier)), Decimal(str(self.settings.target_rr)))
        stop_bps = stop_distance / entry * Decimal(10_000)
        planned_risk = account.current_equity * Decimal(str(self.settings.risk_per_trade))
        plan_values = {
            "entry_reference_price": entry, "stop_loss_price": stop, "take_profit_price": take_profit,
            "stop_distance": stop_distance, "stop_distance_bps": stop_bps, "planned_risk_amount_usdt": planned_risk,
        }
        if stop_bps < Decimal(str(self.settings.min_stop_distance_bps)):
            return base.model_copy(update={**plan_values, "rejection_reasons": ("Stop distance is below the configured minimum",)})
        if stop_bps > Decimal(str(self.settings.max_stop_distance_bps)):
            return base.model_copy(update={**plan_values, "rejection_reasons": ("Stop distance exceeds the configured maximum",)})

        raw_quantity, raw_notional = size_from_risk(planned_risk, stop_distance, entry)
        maximum_notional = account.current_equity * Decimal(str(self.settings.max_position_notional_multiplier))
        notional, quantity, actual_risk = cap_notional(raw_notional, entry, stop_distance, maximum_notional)
        reward = quantity * stop_distance * Decimal(str(self.settings.target_rr))
        rr = reward / actual_risk if actual_risk > 0 else Decimal(0)
        estimated_fees = notional * Decimal(2) * Decimal(str(self.settings.estimated_fee_bps)) / Decimal(10_000)
        estimated_slippage = notional * Decimal(2) * Decimal(str(self.settings.estimated_slippage_bps)) / Decimal(10_000)
        net_reward = reward - estimated_fees - estimated_slippage
        reasons = account_rejection_reasons(account, actual_risk, self.settings)
        if rr < Decimal(str(self.settings.min_rr)):
            reasons.append("Risk-reward ratio is below the configured minimum")
        if net_reward <= 0:
            reasons.append("Estimated costs eliminate the expected reward")
        return base.model_copy(update={
            **plan_values, "actual_risk_amount_usdt": actual_risk, "risk_amount_usdt": actual_risk,
            "position_notional_usdt": notional, "estimated_quantity": quantity, "reward_amount_usdt": reward,
            "risk_reward_ratio": rr, "estimated_fees_usdt": estimated_fees,
            "estimated_slippage_usdt": estimated_slippage, "net_reward_usdt": net_reward,
            "approved": not reasons, "rejection_reasons": tuple(reasons),
        })

    def _base_plan(self, signal: SignalSnapshot, now: datetime) -> TradePlan:
        return TradePlan(
            plan_id=f"plan:{signal.symbol}:{signal.timeframe}:{signal.candle_open_time.isoformat()}" if signal.candle_open_time else "",
            source_signal_id=signal.signal_id or None, symbol=signal.symbol, timeframe=signal.timeframe, direction=signal.direction,
            signal_score=signal.score, signal_confidence=signal.confidence, generated_at=now,
            source_candle_open_time=signal.candle_open_time, source_candle_close_time=signal.candle_close_time,
        )

    async def latest(self, symbol: str) -> TradePlan:
        return await self.store.latest(symbol, self.settings.default_timeframe) or TradePlan(symbol=symbol, timeframe=self.settings.default_timeframe, rejection_reasons=("No risk plan available",))

    async def history(self, symbol: str, limit: int) -> list[TradePlan]:
        return await self.store.history(symbol, self.settings.default_timeframe, limit)

    async def account_state(self) -> RiskAccountState:
        return await self.store.account_state()
