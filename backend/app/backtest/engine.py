"""Chronological no-lookahead replay that composes existing production engines."""

import logging
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.backtest.analytics import equity_point, performance_slice
from app.backtest.data import HistoricalDataLoader
from app.backtest.models import BacktestRequest, BacktestResult, BacktestTrade
from app.backtest.store import BacktestStore
from app.config import Settings
from app.execution.paper_engine import PaperExecutionEngine
from app.market.models import Candle, FeedState, MarketFeedStatus, SymbolFeedStatus
from app.risk.engine import RiskEngine
from app.risk.models import TradePlan
from app.strategy.engine import StrategyEngine
from app.strategy.models import SignalDirection, SignalSnapshot
from app.indicators.engine import IndicatorEngine
from app.indicators.models import IndicatorSnapshot

logger = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(self, settings: Settings, data_root: Path | None = None) -> None:
        self.settings = settings
        self.loader = HistoricalDataLoader(data_root or Path(__file__).resolve().parents[3] / "data" / "backtest", set(settings.symbols))
        self.store = BacktestStore(settings.max_backtest_runs)

    async def run(self, request: BacktestRequest, candles_by_symbol: dict[str, list[Candle]] | None = None) -> BacktestResult:
        self._validate(request)
        logger.info("Backtest started for %s", ", ".join(request.symbols))
        candle_map = candles_by_symbol or {symbol: await self.loader.load(symbol, request.timeframe, request.start_time, request.end_time) for symbol in request.symbols}
        ordered = sorted((candle for candles in candle_map.values() for candle in candles if request.start_time <= candle.open_time and candle.close_time <= request.end_time), key=lambda candle: (candle.open_time, candle.symbol))
        result = await self._replay(request, ordered)
        self.store.save(result)
        logger.info("Backtest completed: %s, %s trades", result.run_id, result.total_trades)
        return result

    def _validate(self, request: BacktestRequest) -> None:
        if request.timeframe != self.settings.default_timeframe:
            raise ValueError("only the configured timeframe is supported")
        if any(symbol.upper() not in self.settings.symbols for symbol in request.symbols):
            raise ValueError("unknown configured symbol")
        if (request.end_time - request.start_time).days > self.settings.max_backtest_days:
            raise ValueError("requested range exceeds max_backtest_days")

    async def _replay(self, request: BacktestRequest, candles: list[Candle]) -> BacktestResult:
        clock = [request.start_time]
        symbols = tuple(symbol.upper() for symbol in request.symbols)
        def feed() -> MarketFeedStatus:
            return MarketFeedStatus(exchange="historical", status=FeedState.CONNECTED, timeframe=request.timeframe, symbols={symbol: SymbolFeedStatus(status=FeedState.CONNECTED) for symbol in symbols})
        replay_settings = self.settings.model_copy(update={"starting_balance": self.settings.backtest_starting_balance})
        plans: dict[str, TradePlan] = {}
        signal_counts = {"long": 0, "short": 0, "no_trade": 0}
        approved = [0]
        rejected = [0]
        rejection_counts: dict[str, int] = {}
        indicators = IndicatorEngine(replay_settings)
        risk = RiskEngine(replay_settings, market_status_provider=feed, now_provider=lambda: clock[0])
        paper = PaperExecutionEngine(replay_settings, market_status_provider=feed, risk_account_sink=risk.store.replace_account_state, now_provider=lambda: clock[0])

        async def on_plan(plan: TradePlan) -> None:
            identity = paper.plan_identity(plan)
            if identity:
                plans[identity] = plan
            if plan.approved:
                approved[0] += 1
            else:
                rejected[0] += 1
                for reason in plan.rejection_reasons:
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            await paper.process_plan(plan)

        risk.set_plan_handler(on_plan)

        async def on_signal(signal: SignalSnapshot) -> None:
            signal_counts[signal.direction.value] = signal_counts.get(signal.direction.value, 0) + 1
            await risk.process_signal(signal)

        strategy = StrategyEngine(replay_settings, market_status_provider=feed, on_signal=on_signal)
        async def on_snapshot(snapshot: IndicatorSnapshot) -> None:
            await strategy.process_snapshot(snapshot)

        indicators.set_snapshot_handler(on_snapshot)
        await paper.sync_risk_account()
        curve = []
        peak = Decimal(str(replay_settings.backtest_starting_balance))
        for candle in candles:
            clock[0] = candle.close_time
            # Process existing pending/open paper state first. Pending entries use N+1 OPEN.
            await paper.process_market_candle(candle, entry_price=candle.open)
            await indicators.process_candle(candle)
            account = await paper.account()
            peak = max(peak, account.equity)
            curve.append(equity_point(candle.close_time, account.equity, peak))
        trades = self._journal(await paper.trades(replay_settings.max_paper_trade_history), plans)
        account = await paper.account()
        return self._result(request, account.starting_balance, account.equity, trades, curve, signal_counts, approved[0], rejected[0], rejection_counts, replay_settings)

    @staticmethod
    def _journal(trades, plans) -> list[BacktestTrade]:
        journal = []
        for trade in trades:
            identity = trade.position_id.removeprefix("paper:")
            plan = plans.get(identity)
            risk = plan.planned_risk_amount_usdt if plan else None
            journal.append(BacktestTrade(symbol=trade.symbol, direction=trade.direction, signal_time=trade.source_signal_time, entry_time=trade.opened_at, entry_price=trade.entry_fill_price, stop_loss_price=plan.stop_loss_price if plan else None, take_profit_price=plan.take_profit_price if plan else None, exit_time=trade.closed_at, exit_price=trade.exit_fill_price, exit_reason=trade.exit_reason, quantity=trade.quantity, planned_risk_amount=risk, gross_pnl=trade.gross_pnl_usdt, fees=trade.fees_usdt, net_pnl=trade.net_pnl_usdt, r_multiple=(trade.net_pnl_usdt / risk if risk else None), signal_score=plan.signal_score if plan else 0))
        return journal

    @staticmethod
    def _result(request, starting, ending, trades, curve, signals, approved, rejected, rejections, settings) -> BacktestResult:
        wins = [trade for trade in trades if trade.net_pnl > 0]
        losses = [trade for trade in trades if trade.net_pnl < 0]
        gross_profit = sum((trade.net_pnl for trade in wins), Decimal(0))
        gross_loss = sum((trade.net_pnl for trade in losses), Decimal(0))
        r_values = [trade.r_multiple for trade in trades if trade.r_multiple is not None]
        symbols = {symbol: performance_slice([trade for trade in trades if trade.symbol == symbol]) for symbol in request.symbols}
        directions = {direction.value: performance_slice([trade for trade in trades if trade.direction == direction]) for direction in (SignalDirection.LONG, SignalDirection.SHORT)}
        return BacktestResult(run_id=str(uuid4()), symbols=tuple(request.symbols), timeframe=request.timeframe, start_time=request.start_time, end_time=request.end_time, starting_balance=starting, ending_balance=ending, total_trades=len(trades), wins=len(wins), losses=len(losses), breakeven_trades=len(trades) - len(wins) - len(losses), gross_profit=gross_profit, gross_loss=gross_loss, gross_pnl=sum((trade.gross_pnl for trade in trades), Decimal(0)), net_pnl=sum((trade.net_pnl for trade in trades), Decimal(0)), total_fees=sum((trade.fees for trade in trades), Decimal(0)), total_slippage_cost=Decimal(0), win_rate=(Decimal(len(wins)) / Decimal(len(trades)) if trades else None), profit_factor=(gross_profit / abs(gross_loss) if gross_loss else None), expectancy_per_trade=(sum((trade.net_pnl for trade in trades), Decimal(0)) / len(trades) if trades else None), max_drawdown_usdt=max((point.drawdown_usdt for point in curve), default=Decimal(0)), max_drawdown_percent=max((point.drawdown_percent for point in curve), default=Decimal(0)), largest_win=max((trade.net_pnl for trade in wins), default=None), largest_loss=min((trade.net_pnl for trade in losses), default=None), average_win=(gross_profit / len(wins) if wins else None), average_loss=(gross_loss / len(losses) if losses else None), average_r_multiple=(sum(r_values, Decimal(0)) / len(r_values) if r_values else None), return_percent=((ending - starting) / starting * Decimal(100) if starting else Decimal(0)), signal_counts=signals, approved_plans=approved, rejected_plans=rejected, rejection_counts=rejections, symbol_performance=symbols, direction_performance=directions, config_snapshot={"risk_per_trade": settings.risk_per_trade, "paper_fee_bps": settings.paper_fee_bps, "entry_slippage_bps": settings.paper_entry_slippage_bps, "exit_slippage_bps": settings.paper_exit_slippage_bps, "ema_fast_period": settings.ema_fast_period, "ema_slow_period": settings.ema_slow_period}, trades=tuple(trades), equity_curve=tuple(curve))
