import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.execution.models import ExitReason
from app.execution.paper_engine import PaperExecutionEngine
from app.indicators.models import IndicatorSnapshot
from app.main import app
from app.market.models import Candle, FeedState, MarketFeedStatus, SymbolFeedStatus
from app.risk.engine import RiskEngine
from app.risk.models import TradePlan
from app.strategy.engine import StrategyEngine
from app.strategy.models import SignalDirection

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)


def status(state: FeedState = FeedState.CONNECTED) -> MarketFeedStatus:
    return MarketFeedStatus(exchange="binance", status=state, timeframe="1m", symbols={symbol: SymbolFeedStatus(status=state) for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")})


def candle(symbol: str, minute: int, close: str, high: str | None = None, low: str | None = None) -> Candle:
    opened = NOW + timedelta(minutes=minute)
    price = Decimal(close)
    return Candle(symbol=symbol, timeframe="1m", open_time=opened, close_time=opened + timedelta(minutes=1) - timedelta(milliseconds=1), open=price, high=Decimal(high or close), low=Decimal(low or close), close=price, volume=Decimal("10"), is_closed=False)


def plan(direction: SignalDirection = SignalDirection.LONG, minute: int = 0, **updates: object) -> TradePlan:
    opened = NOW + timedelta(minutes=minute)
    values: dict[str, object] = {
        "symbol": "BTCUSDT", "timeframe": "1m", "direction": direction, "signal_score": 100,
        "signal_confidence": 1, "entry_reference_price": Decimal("100"),
        "stop_loss_price": Decimal("99") if direction == SignalDirection.LONG else Decimal("101"),
        "take_profit_price": Decimal("102") if direction == SignalDirection.LONG else Decimal("98"),
        "planned_risk_amount_usdt": Decimal("1"), "actual_risk_amount_usdt": Decimal("1"),
        "risk_amount_usdt": Decimal("1"), "position_notional_usdt": Decimal("100"),
        "estimated_quantity": Decimal("1"), "reward_amount_usdt": Decimal("2"), "risk_reward_ratio": Decimal("2"),
        "approved": True, "generated_at": NOW, "source_candle_open_time": opened,
        "source_candle_close_time": opened + timedelta(minutes=1) - timedelta(milliseconds=1),
    }
    values.update(updates)
    return TradePlan(**values)


def paper(now: datetime = NOW, market: MarketFeedStatus | None = None):
    synced = []
    events = []
    async def sink(value): synced.append(value)
    async def emit(value): events.append(value)
    engine = PaperExecutionEngine(Settings(), market_status_provider=lambda: market or status(), risk_account_sink=sink, on_event=emit, now_provider=lambda: now)
    return engine, synced, events


def test_entry_long_short_exits_and_account_updates() -> None:
    async def exercise() -> None:
        long_engine, synced, events = paper()
        assert await long_engine.process_plan(plan())
        await long_engine.process_market_candle(candle("BTCUSDT", 1, "100"))
        position = (await long_engine.positions())[0]
        assert position.entry_fill_price == Decimal("100.0200")
        assert position.entry_fee_usdt == Decimal("0.1000200")
        await long_engine.process_market_candle(candle("BTCUSDT", 2, "101", high="101", low="100"))
        await long_engine.process_market_candle(candle("BTCUSDT", 2, "102", high="102", low="100"))
        trade = (await long_engine.trades(10))[0]
        assert trade.exit_reason == ExitReason.TAKE_PROFIT
        assert trade.exit_fill_price == Decimal("101.9796")
        assert trade.net_pnl_usdt > 0
        account = await long_engine.account()
        assert account.equity == account.cash_balance and account.winning_trade_count == 1 and account.win_rate == 1
        assert synced[-1].current_equity == account.equity
        event_types = {event["type"] for event in events}
        assert {"paper.plan_pending", "paper.position_opened", "paper.position_updated", "paper.position_closed", "paper.account_updated"} <= event_types

        short_engine, _, _ = paper()
        assert await short_engine.process_plan(plan(SignalDirection.SHORT))
        await short_engine.process_market_candle(candle("BTCUSDT", 1, "100"))
        short_position = (await short_engine.positions())[0]
        assert short_position.entry_fill_price == Decimal("99.9800")
        await short_engine.process_market_candle(candle("BTCUSDT", 2, "98", high="100", low="98"))
        short_trade = (await short_engine.trades(10))[0]
        assert short_trade.exit_reason == ExitReason.TAKE_PROFIT and short_trade.net_pnl_usdt > 0
    asyncio.run(exercise())


def test_stop_collision_guards_and_deduplication() -> None:
    async def exercise() -> None:
        engine, _, _ = paper()
        assert await engine.process_plan(plan())
        assert not await engine.process_plan(plan())
        await engine.process_market_candle(candle("BTCUSDT", 1, "100"))
        # Both levels crossed: conservative policy exits the long at its stop first.
        await engine.process_market_candle(candle("BTCUSDT", 2, "100", high="103", low="98"))
        trade = (await engine.trades(10))[0]
        assert trade.exit_reason == ExitReason.STOP_LOSS and trade.net_pnl_usdt < 0
        assert len(await engine.trades(10)) == 1

        rejected = plan(approved=False, minute=3)
        assert not await engine.process_plan(rejected)
        stale = plan(minute=4, generated_at=NOW - timedelta(seconds=91))
        assert not await engine.process_plan(stale)
        unhealthy, _, _ = paper(market=status(FeedState.STALE))
        assert await unhealthy.process_plan(plan())
        await unhealthy.process_market_candle(candle("BTCUSDT", 1, "100"))
        assert await unhealthy.positions() == []
    asyncio.run(exercise())


def test_gap_through_stop_uses_candle_open_before_slippage() -> None:
    async def exercise() -> None:
        engine, _, _ = paper()
        assert await engine.process_plan(plan())
        await engine.process_market_candle(candle("BTCUSDT", 1, "100"))
        await engine.process_market_candle(candle("BTCUSDT", 2, "95", high="95", low="95"))
        trade = (await engine.trades(10))[0]
        assert trade.exit_reason == ExitReason.STOP_LOSS
        assert trade.exit_fill_price == Decimal("94.9810")
    asyncio.run(exercise())


def test_global_position_limit_daily_reset_and_risk_feedback() -> None:
    async def exercise() -> None:
        engine, synced, _ = paper()
        assert await engine.process_plan(plan())
        eth_plan = plan(minute=1, symbol="ETHUSDT")
        assert await engine.process_plan(eth_plan)
        await engine.process_market_candle(candle("BTCUSDT", 1, "100"))
        await engine.process_market_candle(candle("ETHUSDT", 2, "100"))
        assert len(await engine.positions()) == 1
        await engine.process_market_candle(candle("BTCUSDT", 3, "99", high="100", low="99"))
        account = await engine.account()
        assert account.realized_pnl_today < 0 and synced[-1].realized_pnl_today == account.realized_pnl_today

        later = NOW + timedelta(days=1)
        reset_engine, _, _ = paper(now=later)
        reset_engine.store.account = reset_engine.store.account.model_copy(update={"statistics_day": NOW.date(), "realized_pnl_today": Decimal("-1"), "realized_pnl": Decimal("-1"), "equity": Decimal("99")})
        assert (await reset_engine.account()).realized_pnl_today == 0
        assert (await reset_engine.account()).realized_pnl == Decimal("-1")
    asyncio.run(exercise())


def test_synthetic_signal_to_risk_to_paper_end_to_end_and_apis() -> None:
    async def exercise() -> None:
        market = status()
        risk = RiskEngine(Settings(), market_status_provider=lambda: market, now_provider=lambda: NOW)
        paper_engine, _, _ = paper()
        paper_engine._risk_account_sink = risk.store.replace_account_state
        risk.set_plan_handler(paper_engine.process_plan)
        strategy = StrategyEngine(Settings(), market_status_provider=lambda: market)
        indicator = IndicatorSnapshot(symbol="BTCUSDT", timeframe="1m", candle_open_time=NOW, candle_close_time=NOW + timedelta(minutes=1) - timedelta(milliseconds=1), close=Decimal("100"), ema_9=Decimal("101"), ema_21=Decimal("100"), rsi_14=Decimal("60"), atr_14=Decimal("0.5"), vwap=Decimal("99"), volume=Decimal("20"), volume_ma_20=Decimal("10"), is_ready=True, calculated_at=NOW)
        signal_snapshot = await strategy.process_snapshot(indicator)
        assert signal_snapshot is not None and signal_snapshot.is_actionable
        plan_snapshot = await risk.process_signal(signal_snapshot)
        assert plan_snapshot is not None and plan_snapshot.approved
        await paper_engine.process_market_candle(candle("BTCUSDT", 1, "100"))
        assert (await risk.account_state()).open_position_count == 1
        await paper_engine.process_market_candle(candle("BTCUSDT", 2, "102", high="102", low="100"))
        assert len(await paper_engine.trades(10)) == 1
        assert (await risk.account_state()).current_equity == (await paper_engine.account()).equity
    asyncio.run(exercise())

    with TestClient(app) as client:
        assert client.get("/api/paper/account").status_code == 200
        assert client.get("/api/paper/positions").json() == []
        assert client.get("/api/paper/trades?limit=10").json() == []
    event_types = {"paper.plan_pending", "paper.position_opened", "paper.position_updated", "paper.position_closed", "paper.account_updated"}
    assert all(event_type.startswith("paper.") for event_type in event_types)


def test_execution_config_fails_closed() -> None:
    with pytest.raises(ValueError, match="execution mode"):
        Settings(execution_mode="live")
