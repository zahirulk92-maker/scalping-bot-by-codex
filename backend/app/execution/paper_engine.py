"""Central deterministic PAPER execution lifecycle, with no exchange integrations."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.db.models import RecoveryStatus
from app.db.repositories.paper import PaperRepository
from app.execution.fills import entry_fill, exit_fill, fee, gross_pnl
from app.execution.models import ClosedPaperTrade, ExitReason, PaperAccount, PaperPosition, PositionStatus
from app.execution.store import PaperExecutionStore
from app.market.models import Candle, FeedState, MarketFeedStatus
from app.risk.models import RiskAccountState, TradePlan
from app.strategy.models import SignalDirection

logger = logging.getLogger(__name__)
EventHandler = Callable[[dict[str, Any]], Awaitable[None]]
RiskAccountSink = Callable[[RiskAccountState], Awaitable[None]]
MarketStatusProvider = Callable[[], MarketFeedStatus]
NowProvider = Callable[[], datetime]


class PaperExecutionEngine:
    """Executes only approved plans against subsequent public market observations."""

    def __init__(self, settings: Settings, market_status_provider: MarketStatusProvider, risk_account_sink: RiskAccountSink, on_event: EventHandler | None = None, now_provider: NowProvider | None = None, repository: PaperRepository | None = None, session_id: str | None = None) -> None:
        self.settings = settings
        self._market_status_provider = market_status_provider
        self._risk_account_sink = risk_account_sink
        self._on_event = on_event
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._repository = repository
        self._session_id = session_id
        self.recovery_status = RecoveryStatus.COMPLETE
        self.entries_paused = False
        now = self._now()
        self.store = PaperExecutionStore(settings, PaperAccount(starting_balance=Decimal(str(settings.starting_balance)), cash_balance=Decimal(str(settings.starting_balance)), equity=Decimal(str(settings.starting_balance)), statistics_day=now.date()))
        self._lock = asyncio.Lock()
        logger.info("Paper execution engine initialized; no real orders can be placed")

    @staticmethod
    def plan_identity(plan: TradePlan) -> str | None:
        if plan.source_candle_open_time is None:
            return None
        return f"{plan.symbol}:{plan.timeframe}:{plan.source_candle_open_time.isoformat()}"

    async def sync_risk_account(self) -> None:
        await self._risk_account_sink(self._risk_state())

    async def process_plan(self, plan: TradePlan) -> bool:
        identity = self.plan_identity(plan)
        if identity is None:
            return False
        async with self._lock:
            await self._reset_day_if_needed()
            if self.recovery_status != RecoveryStatus.COMPLETE:
                logger.warning("Paper plan blocked while recovery state is %s", self.recovery_status)
                return False
            if self.entries_paused:
                logger.warning("Paper plan blocked by validation gate")
                return False
            if identity in self.store.seen_plan_ids:
                return False
            self.store.seen_plan_ids.append(identity)
            if not self._valid_plan(plan):
                logger.info("Paper plan rejected for %s", plan.symbol)
                return False
            self.store.pending[identity] = plan
        await self._emit("paper.plan_pending", plan)
        return True

    def set_entries_paused(self, paused: bool) -> None:
        """Pause only new simulated entries; existing positions remain monitored."""
        self.entries_paused = paused

    async def process_market_candle(self, candle: Candle, entry_price: Decimal | None = None) -> None:
        """Use real public observations: existing positions first, then pending fills."""
        async with self._lock:
            day_reset = await self._reset_day_if_needed()
            existing = [position for position in self.store.open_positions.values() if position.symbol == candle.symbol]
            events: list[tuple[str, object]] = []
            for position in existing:
                closed = self._update_or_close(position, candle)
                if isinstance(closed, ClosedPaperTrade):
                    self._persist_close(closed)
                    events.append(("paper.position_closed", closed))
                else:
                    if candle.is_closed:
                        self._persist_open(closed)
                    events.append(("paper.position_updated", closed))
            for identity, plan in list(self.store.pending.items()):
                if plan.symbol != candle.symbol:
                    continue
                opened_position = self._open_from_plan(identity, plan, candle, entry_price or candle.close)
                self.store.pending.pop(identity, None)
                if opened_position is not None:
                    self._persist_open(opened_position)
                    events.append(("paper.position_opened", opened_position))
            account_changed = bool(events) or day_reset
        for event_type, data in events:
            await self._emit(event_type, data)
        if account_changed:
            await self._sync_and_emit_account()

    def _valid_plan(self, plan: TradePlan) -> bool:
        if not plan.approved or plan.direction not in (SignalDirection.LONG, SignalDirection.SHORT):
            return False
        if plan.generated_at is None or (self._now() - plan.generated_at).total_seconds() > self.settings.max_signal_age_seconds:
            return False
        if any(value is None for value in (plan.entry_reference_price, plan.stop_loss_price, plan.take_profit_price, plan.estimated_quantity, plan.risk_amount_usdt, plan.source_candle_open_time, plan.source_candle_close_time)):
            return False
        return True

    def _market_healthy(self, symbol: str) -> bool:
        status = self._market_status_provider()
        symbol_status = status.symbols.get(symbol)
        state = symbol_status.status if symbol_status else status.status
        return state not in (FeedState.STALE, FeedState.DISCONNECTED, FeedState.ERROR)

    def _open_from_plan(self, identity: str, plan: TradePlan, candle: Candle, observed_entry_price: Decimal) -> PaperPosition | None:
        if not self._valid_plan(plan) or not self._market_healthy(plan.symbol) or len(self.store.open_positions) >= self.settings.max_open_positions:
            logger.info("Paper plan cancelled before fill for %s", plan.symbol)
            return None
        entry_reference = plan.entry_reference_price
        stop = plan.stop_loss_price
        target = plan.take_profit_price
        quantity = plan.estimated_quantity
        risk_amount = plan.risk_amount_usdt
        source_open = plan.source_candle_open_time
        source_close = plan.source_candle_close_time
        assert entry_reference is not None and stop is not None and target is not None
        assert quantity is not None and risk_amount is not None and source_open is not None and source_close is not None
        fill_price = entry_fill(observed_entry_price, plan.direction, Decimal(str(self.settings.paper_entry_slippage_bps)))
        notional = fill_price * quantity
        entry_fee = fee(notional, Decimal(str(self.settings.paper_fee_bps)))
        position_id = f"paper:{identity}"
        position = PaperPosition(
            position_id=position_id, plan_identity=identity, symbol=plan.symbol, timeframe=plan.timeframe,
            direction=plan.direction, entry_reference_price=entry_reference, entry_fill_price=fill_price,
            current_price=candle.close, quantity=quantity, position_notional=notional, stop_loss_price=stop,
            take_profit_price=target, risk_amount_usdt=risk_amount, entry_fee_usdt=entry_fee,
            estimated_exit_fee_usdt=fee(candle.close * quantity, Decimal(str(self.settings.paper_fee_bps))),
            opened_at=self._now(), source_signal_time=plan.generated_at, source_candle_open_time=source_open,
            source_candle_close_time=source_close, source_plan_id=plan.plan_id or None, last_processed_at=candle.close_time,
        )
        position = self._mark_position(position, candle.close)
        self.store.open_positions[position_id] = position
        self.store.account = self.store.account.model_copy(update={"cash_balance": self.store.account.cash_balance - entry_fee, "fees_paid": self.store.account.fees_paid + entry_fee, "open_position_count": len(self.store.open_positions)})
        self._revalue_equity()
        logger.info("Paper position opened: %s %s", plan.direction.value, plan.symbol)
        return position

    def _update_or_close(self, position: PaperPosition, candle: Candle) -> PaperPosition | ClosedPaperTrade:
        # Conservative OHLC policy: if both levels are inside an unknown candle, stop wins.
        stop_hit = candle.low <= position.stop_loss_price if position.direction == SignalDirection.LONG else candle.high >= position.stop_loss_price
        target_hit = candle.high >= position.take_profit_price if position.direction == SignalDirection.LONG else candle.low <= position.take_profit_price
        if stop_hit:
            gap_price = candle.open if (position.direction == SignalDirection.LONG and candle.open <= position.stop_loss_price) or (position.direction == SignalDirection.SHORT and candle.open >= position.stop_loss_price) else position.stop_loss_price
            return self._close(position, gap_price, ExitReason.STOP_LOSS)
        if target_hit:
            gap_price = candle.open if (position.direction == SignalDirection.LONG and candle.open >= position.take_profit_price) or (position.direction == SignalDirection.SHORT and candle.open <= position.take_profit_price) else position.take_profit_price
            return self._close(position, gap_price, ExitReason.TAKE_PROFIT)
        updated = self._mark_position(position, candle.close).model_copy(update={"last_processed_at": candle.close_time})
        self.store.open_positions[position.position_id] = updated
        self._revalue_equity()
        return updated

    def _mark_position(self, position: PaperPosition, price: Decimal) -> PaperPosition:
        estimated_exit_fee = fee(price * position.quantity, Decimal(str(self.settings.paper_fee_bps)))
        gross = gross_pnl(position.entry_fill_price, price, position.quantity, position.direction)
        return position.model_copy(update={"current_price": price, "estimated_exit_fee_usdt": estimated_exit_fee, "unrealized_gross_pnl": gross, "unrealized_net_pnl": gross - estimated_exit_fee})

    def _close(self, position: PaperPosition, trigger: Decimal, reason: ExitReason) -> ClosedPaperTrade:
        fill_price = exit_fill(trigger, position.direction, Decimal(str(self.settings.paper_exit_slippage_bps)))
        exit_fee = fee(fill_price * position.quantity, Decimal(str(self.settings.paper_fee_bps)))
        gross = gross_pnl(position.entry_fill_price, fill_price, position.quantity, position.direction)
        total_fees = position.entry_fee_usdt + exit_fee
        net = gross - total_fees
        trade = ClosedPaperTrade(trade_id=f"trade:{position.position_id}", position_id=position.position_id, symbol=position.symbol, direction=position.direction, entry_fill_price=position.entry_fill_price, exit_fill_price=fill_price, quantity=position.quantity, risk_amount_usdt=position.risk_amount_usdt, gross_pnl_usdt=gross, fees_usdt=total_fees, net_pnl_usdt=net, exit_reason=reason, opened_at=position.opened_at, closed_at=self._now(), source_signal_time=position.source_signal_time)
        self.store.open_positions.pop(position.position_id, None)
        self.store.closed_trades.append(trade)
        self.store.latest_trade_by_symbol[position.symbol] = trade
        account = self.store.account
        closed_count = account.closed_trade_count + 1
        wins = account.winning_trade_count + (1 if net > 0 else 0)
        self.store.account = account.model_copy(update={"cash_balance": account.cash_balance + gross - exit_fee, "equity": account.cash_balance + gross - exit_fee, "realized_pnl": account.realized_pnl + net, "realized_pnl_today": account.realized_pnl_today + net, "gross_pnl": account.gross_pnl + gross, "fees_paid": account.fees_paid + exit_fee, "open_position_count": len(self.store.open_positions), "closed_trade_count": closed_count, "winning_trade_count": wins, "losing_trade_count": account.losing_trade_count + (1 if net < 0 else 0), "win_rate": Decimal(wins) / Decimal(closed_count)})
        logger.info("Paper position closed: %s %s, net PnL=%s", reason.value, position.symbol, net)
        return trade

    def _revalue_equity(self) -> None:
        net = sum((position.unrealized_net_pnl for position in self.store.open_positions.values()), Decimal(0))
        self.store.account = self.store.account.model_copy(update={"equity": self.store.account.cash_balance + net, "open_position_count": len(self.store.open_positions)})

    async def _reset_day_if_needed(self) -> bool:
        today = self._now().date()
        if self.store.account.statistics_day != today:
            self.store.account = self.store.account.model_copy(update={"statistics_day": today, "realized_pnl_today": Decimal(0)})
            self._persist_account()
            logger.info("Paper daily statistics reset at 00:00 UTC")
            return True
        return False

    def _risk_state(self) -> RiskAccountState:
        account = self.store.account
        return RiskAccountState(current_equity=account.equity, realized_pnl_today=account.realized_pnl_today, open_position_count=account.open_position_count)

    async def _sync_and_emit_account(self) -> None:
        await self._risk_account_sink(self._risk_state())
        await self._emit("paper.account_updated", self.store.account)

    def _persist_account(self) -> None:
        if self._repository and self._session_id:
            self._repository.persist_account(self._session_id, self.store.account)

    def _persist_open(self, position: PaperPosition) -> None:
        if self._repository and self._session_id:
            self._repository.persist_open(self._session_id, self.store.account, position)

    def _persist_close(self, trade: ClosedPaperTrade) -> None:
        if self._repository and self._session_id:
            self._repository.persist_close(self._session_id, self.store.account, trade)

    async def restore_state(self, account: PaperAccount | None, positions: list[PaperPosition], trades: list[ClosedPaperTrade]) -> None:
        """Restore only durable PAPER state; recovered positions stay fail-closed."""
        async with self._lock:
            if account is not None:
                self.store.account = account
            self.store.open_positions = {
                position.position_id: position.model_copy(update={"status": PositionStatus.RECOVERY_PENDING})
                for position in positions
            }
            self.store.closed_trades.extend(trades[-self.settings.max_paper_trade_history:])
            for trade in trades:
                self.store.latest_trade_by_symbol[trade.symbol] = trade
            self.store.account = self.store.account.model_copy(update={"open_position_count": len(self.store.open_positions)})
            self.recovery_status = RecoveryStatus.PENDING if positions else RecoveryStatus.COMPLETE
        await self.sync_risk_account()

    async def reconcile_recovered_positions(self, fetch_historical: Callable[[str, str, int], Awaitable[list[Candle]]]) -> None:
        """Replay public missed candles with the normal stop-first simulator policy."""
        if self.recovery_status != RecoveryStatus.PENDING:
            return
        try:
            async with self._lock:
                recovered = list(self.store.open_positions.values())
            for position in recovered:
                candles = await fetch_historical(position.symbol, position.timeframe, self.settings.recovery_history_limit)
                for candle in sorted((item for item in candles if item.close_time > (position.last_processed_at or position.source_candle_close_time)), key=lambda item: item.open_time):
                    async with self._lock:
                        active = self.store.open_positions.get(position.position_id)
                        if active is None:
                            break
                        outcome = self._update_or_close(active, candle)
                        if isinstance(outcome, ClosedPaperTrade):
                            self._persist_close(outcome)
                        else:
                            self.store.open_positions[outcome.position_id] = outcome
                async with self._lock:
                    active = self.store.open_positions.get(position.position_id)
                    if active:
                        self.store.open_positions[position.position_id] = active.model_copy(update={"status": PositionStatus.OPEN})
            async with self._lock:
                self.recovery_status = RecoveryStatus.COMPLETE
                self._persist_account()
            await self._sync_and_emit_account()
            await self._emit("paper.recovery", {"status": RecoveryStatus.COMPLETE.value})
            logger.info("Paper recovery completed")
        except Exception as error:
            self.recovery_status = RecoveryStatus.ERROR
            await self._emit("paper.recovery", {"status": RecoveryStatus.ERROR.value, "message": str(error)})
            logger.exception("Paper recovery failed; new entries remain blocked")


    async def _emit(self, event_type: str, data: object) -> None:
        if self._on_event:
            payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
            await self._on_event({"type": event_type, "data": payload})

    async def account(self) -> PaperAccount:
        async with self._lock:
            await self._reset_day_if_needed()
            return self.store.account

    async def positions(self) -> list[PaperPosition]:
        async with self._lock:
            return list(self.store.open_positions.values())

    async def trades(self, limit: int) -> list[ClosedPaperTrade]:
        async with self._lock:
            return list(self.store.closed_trades)[-limit:]
