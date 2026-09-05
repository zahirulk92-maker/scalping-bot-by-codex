"""Advanced Futures Demo Trading Engine for Phase 13."""

import logging
import uuid
import httpx
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Awaitable, List, Optional, Dict

from app.config import Settings
from app.market.provider import MarketStatusProvider
from app.market.models import Candle
from app.strategy.models import TradePlan, SignalDirection
from app.risk.sink import RiskAccountSink
from app.execution.events import EventHandler
from app.execution.models import PositionStatus, ExitReason, ExecutionResult
from app.execution.futures_models import (
    FuturesDemoAccount, FuturesDemoPosition, FuturesDemoFill, FundingEvent, 
    LiquidationEvent, FuturesSymbolRules, DemoOrderIntent, DemoOrder
)

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
        self._orders: dict[str, DemoOrder] = {}
        self._intents: dict[str, DemoOrderIntent] = {}
        self._fills: dict[str, FuturesDemoFill] = {}
        self._rules: dict[str, FuturesSymbolRules] = {}
        self._entries_paused = False
        
        self.http_client = httpx.AsyncClient()

    async def _fetch_symbol_rules(self, symbol: str) -> FuturesSymbolRules:
        if symbol in self._rules:
            return self._rules[symbol]
            
        try:
            res = await self.http_client.get("https://fapi.binance.com/fapi/v1/exchangeInfo")
            data = res.json()
            for s in data['symbols']:
                if s['symbol'] == symbol:
                    filters = {f['filterType']: f for f in s['filters']}
                    tick_size = Decimal(filters['PRICE_FILTER']['tickSize'])
                    step_size = Decimal(filters['LOT_SIZE']['stepSize'])
                    min_qty = Decimal(filters['LOT_SIZE']['minQty'])
                    max_qty = Decimal(filters['LOT_SIZE']['maxQty'])
                    min_notional = Decimal(filters.get('MIN_NOTIONAL', {}).get('notional', '5.0'))
                    
                    rules = FuturesSymbolRules(
                        symbol=symbol,
                        status=s['status'],
                        price_tick_size=tick_size,
                        quantity_step_size=step_size,
                        min_price=Decimal(filters['PRICE_FILTER']['minPrice']),
                        max_price=Decimal(filters['PRICE_FILTER']['maxPrice']),
                        min_quantity=min_qty,
                        max_quantity=max_qty,
                        min_notional=min_notional,
                        market_min_quantity=min_qty,
                        market_max_quantity=max_qty,
                        updated_at=datetime.now(timezone.utc)
                    )
                    self._rules[symbol] = rules
                    return rules
        except Exception as e:
            logger.error(f"Failed to fetch exchange info for {symbol}: {e}")
            
        # Fallback
        return FuturesSymbolRules(
            symbol=symbol,
            status="TRADING",
            price_tick_size=Decimal("0.1"),
            quantity_step_size=Decimal("0.001"),
            min_price=Decimal("0.1"),
            max_price=Decimal("1000000"),
            min_quantity=Decimal("0.001"),
            max_quantity=Decimal("1000"),
            min_notional=Decimal("5.0"),
            market_min_quantity=Decimal("0.001"),
            market_max_quantity=Decimal("1000"),
            updated_at=datetime.now(timezone.utc)
        )

    async def _fetch_book_ticker(self, symbol: str) -> tuple[Decimal, Decimal]:
        try:
            res = await self.http_client.get(f"https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol={symbol}")
            data = res.json()
            return Decimal(data['bidPrice']), Decimal(data['askPrice'])
        except Exception:
            # Fallback will be handled by the caller using candle close
            return Decimal(0), Decimal(0)
            
    def _round_price(self, price: Decimal, tick_size: Decimal) -> Decimal:
        return (price / tick_size).quantize(Decimal('1')) * tick_size
        
    def _round_qty(self, qty: Decimal, step_size: Decimal) -> Decimal:
        return (qty / step_size).quantize(Decimal('1')) * step_size

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
                
            # Check liquidation
            if pos.margin_balance <= pos.maintenance_margin:
                closed = await self._liquidate(pos, candle.close)
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
                closed = await self._close_market(pos, pos.stop_loss, ExitReason.STOP_LOSS)
                closed_positions.append(closed)
            elif hit_tp:
                closed = await self._close_market(pos, pos.take_profit, ExitReason.TAKE_PROFIT)
                closed_positions.append(closed)
            else:
                pos = self._mark_position(pos, candle.close)
                self._positions[pos_id] = pos

        if closed_positions:
            self._revalue_equity()
            await self._sync_and_emit_account()

    def _mark_position(self, position: FuturesDemoPosition, price: Decimal) -> FuturesDemoPosition:
        unrealized = (price - position.entry_price) * position.quantity if position.side == SignalDirection.LONG else (position.entry_price - price) * position.quantity
        return position.model_copy(update={"mark_price": price, "unrealized_pnl": unrealized})

    async def _liquidate(self, position: FuturesDemoPosition, price: Decimal) -> FuturesDemoPosition:
        return await self._close_market(position, price, ExitReason.SAFETY_CLOSE)

    async def _close_market(self, position: FuturesDemoPosition, reference_price: Decimal, reason: ExitReason) -> FuturesDemoPosition:
        bid, ask = await self._fetch_book_ticker(position.symbol)
        
        # execution uses adverse side
        if position.side == SignalDirection.LONG:
            exec_price = bid if bid > 0 else reference_price
            exec_price = exec_price * Decimal("0.9995") # dynamic adverse gap slippage
        else:
            exec_price = ask if ask > 0 else reference_price
            exec_price = exec_price * Decimal("1.0005")

        rules = await self._fetch_symbol_rules(position.symbol)
        exec_price = self._round_price(exec_price, rules.price_tick_size)

        unrealized = (exec_price - position.entry_price) * position.quantity if position.side == SignalDirection.LONG else (position.entry_price - exec_price) * position.quantity
        fee = (exec_price * position.quantity) * Decimal(self.settings.futures_demo_taker_fee_bps) / Decimal(10000)
        
        pos = position.model_copy(update={
            "status": PositionStatus.CLOSED,
            "mark_price": exec_price,
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
            
        rules = await self._fetch_symbol_rules(plan.symbol)
        if rules.status != "TRADING":
            return False
            
        bid, ask = await self._fetch_book_ticker(plan.symbol)
        
        # LONG uses ask, SHORT uses bid
        exec_price = ask if plan.direction == SignalDirection.LONG else bid
        if exec_price == 0:
            exec_price = plan.entry_price
            
        exec_price = self._round_price(exec_price, rules.price_tick_size)
            
        qty = plan.risk_amount_usdt / abs(exec_price - plan.stop_loss)
        qty = self._round_qty(qty, rules.quantity_step_size)
        
        if qty < rules.min_quantity or (qty * exec_price) < rules.min_notional:
            return False

        notional = qty * exec_price
        margin = notional / self.settings.futures_demo_leverage
        fee = notional * Decimal(self.settings.futures_demo_taker_fee_bps) / Decimal(10000)
        
        if self._account.free_margin < margin + fee:
            return False
            
        intent = DemoOrderIntent(
            intent_id=str(uuid.uuid4()),
            signal_id=None,
            trade_plan_id=None,
            symbol=plan.symbol,
            side=plan.direction,
            requested_quantity=qty,
            requested_notional=notional,
            created_at=datetime.now(timezone.utc)
        )
        self._intents[intent.intent_id] = intent
            
        pos = FuturesDemoPosition(
            position_id=str(uuid.uuid4()),
            symbol=plan.symbol,
            side=plan.direction,
            quantity=qty,
            entry_price=exec_price,
            mark_price=exec_price,
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
            "realized_pnl": realized,
            "updated_at": datetime.now(timezone.utc)
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
        
    async def close(self):
        await self.http_client.aclose()
