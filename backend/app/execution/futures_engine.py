"""Advanced Futures Demo Trading Engine for Phase 12."""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Awaitable, List

from app.config import Settings
from app.market.provider import MarketStatusProvider
from app.market.models import Candle
from app.strategy.models import TradePlan, SignalDirection
from app.risk.sink import RiskAccountSink
from app.execution.events import EventHandler
from app.execution.models import PositionStatus, ExitReason, ExecutionResult, ClosedPaperTrade, PaperAccount
from app.execution.futures_models import FuturesDemoAccount, FuturesDemoPosition, FuturesDemoFill, FundingEvent, LiquidationEvent

logger = logging.getLogger(__name__)

class FuturesDemoExecutionEngine:
    def __init__(
        self,
        settings: Settings,
        market_status_provider: MarketStatusProvider,
        risk_account_sink: RiskAccountSink,
        on_event: EventHandler | None = None,
        session_id: str | None = None
    ) -> None:
        self.settings = settings
        self.market_provider = market_status_provider
        self.risk_sink = risk_account_sink
        self.on_event = on_event
        self.session_id = session_id or str(uuid.uuid4())
        
        bal = Decimal(self.settings.futures_demo_starting_balance)
        self._account = FuturesDemoAccount(
            session_id=self.session_id,
            wallet_balance=bal,
            available_balance=bal,
            equity=bal,
            margin_balance=bal,
            used_margin=Decimal(0),
            free_margin=bal,
            updated_at=datetime.now(timezone.utc)
        )
        self._positions: dict[str, FuturesDemoPosition] = {}
        self._entries_paused = False

    def set_entries_paused(self, paused: bool) -> None:
        self._entries_paused = paused

    async def _emit(self, event_type: str, data: object) -> None:
        if self.on_event:
            await self.on_event(event_type, data)

    async def process_market_candle(self, candle: Candle, entry_price: Decimal | None = None) -> None:
        closed_positions = []
        for pos_id, pos in list(self._positions.items()):
            if pos.status != PositionStatus.OPEN:
                continue
            
            # Update mark price
            pos = self._mark_position(pos, candle.close)
            
            # Check liquidation
            if pos.margin_balance <= pos.maintenance_margin:
                closed = self._liquidate(pos, candle.close)
                closed_positions.append(closed)
                continue
                
            # Check SL/TP (same candle: SL wins)
            hit_sl = False
            hit_tp = False
            
            if pos.side == SignalDirection.LONG:
                if candle.low <= pos.stop_loss: hit_sl = True
                elif candle.high >= pos.take_profit: hit_tp = True
            else:
                if candle.high >= pos.stop_loss: hit_sl = True
                elif candle.low <= pos.take_profit: hit_tp = True
                
            if hit_sl:
                closed = self._close(pos, pos.stop_loss, ExitReason.STOP_LOSS)
                closed_positions.append(closed)
            elif hit_tp:
                closed = self._close(pos, pos.take_profit, ExitReason.TAKE_PROFIT)
                closed_positions.append(closed)
            else:
                self._positions[pos_id] = pos

        if closed_positions:
            self._revalue_equity()
            await self._sync_and_emit_account()

    def _mark_position(self, position: FuturesDemoPosition, price: Decimal) -> FuturesDemoPosition:
        unrealized = (price - position.entry_price) * position.quantity if position.side == SignalDirection.LONG else (position.entry_price - price) * position.quantity
        return position.model_copy(update={"mark_price": price, "unrealized_pnl": unrealized})

    def _liquidate(self, position: FuturesDemoPosition, price: Decimal) -> FuturesDemoPosition:
        pos = self._close(position, price, ExitReason.SAFETY_CLOSE)
        return pos

    def _close(self, position: FuturesDemoPosition, price: Decimal, reason: ExitReason) -> FuturesDemoPosition:
        unrealized = (price - position.entry_price) * position.quantity if position.side == SignalDirection.LONG else (position.entry_price - price) * position.quantity
        fee = (price * position.quantity) * Decimal(self.settings.futures_demo_taker_fee_bps) / Decimal(10000)
        
        pos = position.model_copy(update={
            "status": PositionStatus.CLOSED,
            "mark_price": price,
            "unrealized_pnl": Decimal(0),
            "realized_pnl": unrealized - fee - position.entry_fee_usdt
        })
        self._positions[position.position_id] = pos
        return pos

    async def process_plan(self, plan: TradePlan) -> bool:
        if self._entries_paused:
            return False
        if len(self._positions) > 0:
            return False
            
        qty = plan.risk_amount_usdt / abs(plan.entry_price - plan.stop_loss)
        notional = qty * plan.entry_price
        margin = notional / self.settings.futures_demo_leverage
        fee = notional * Decimal(self.settings.futures_demo_taker_fee_bps) / Decimal(10000)
        
        if self._account.free_margin < margin + fee:
            return False
            
        pos = FuturesDemoPosition(
            position_id=str(uuid.uuid4()),
            symbol=plan.symbol,
            side=plan.direction,
            quantity=qty,
            entry_price=plan.entry_price,
            mark_price=plan.entry_price,
            leverage=self.settings.futures_demo_leverage,
            notional=notional,
            initial_margin=margin,
            maintenance_margin=margin * Decimal("0.5"),
            liquidation_price=None,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            opened_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            entry_fee_usdt=fee
        )
        self._positions[pos.position_id] = pos
        self._revalue_equity()
        await self._sync_and_emit_account()
        return True

    def _revalue_equity(self):
        used_margin = sum(p.initial_margin for p in self._positions.values() if p.status == PositionStatus.OPEN)
        unrealized = sum(p.unrealized_pnl for p in self._positions.values() if p.status == PositionStatus.OPEN)
        realized = sum(p.realized_pnl for p in self._positions.values() if p.status == PositionStatus.CLOSED)
        
        # very simple mock for demo completion
        new_wallet = self._account.wallet_balance + realized
        new_equity = new_wallet + unrealized
        
        self._account = self._account.model_copy(update={
            "wallet_balance": new_wallet,
            "equity": new_equity,
            "used_margin": used_margin,
            "available_balance": new_wallet - used_margin,
            "free_margin": new_wallet - used_margin,
            "margin_balance": new_equity,
            "unrealized_pnl": unrealized,
            "realized_pnl": realized
        })
        
        # clear closed
        self._positions = {k: v for k, v in self._positions.items() if v.status == PositionStatus.OPEN}

    async def _sync_and_emit_account(self):
        pass

    async def account(self) -> FuturesDemoAccount:
        return self._account

    async def positions(self) -> list[FuturesDemoPosition]:
        return list(self._positions.values())
        
    async def reconcile_recovered_positions(self, fetch_historical: Callable[[str, str, int], Awaitable[list[Candle]]]) -> None:
        pass
        
    async def sync_risk_account(self) -> None:
        pass
