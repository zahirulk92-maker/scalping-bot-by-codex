import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.config import Settings
from app.db.database import Database
from app.db.models import RecoveryStatus
from app.db.repositories.paper import PaperRepository
from app.execution.paper_engine import PaperExecutionEngine
from app.market.models import Candle, FeedState, MarketFeedStatus, SymbolFeedStatus
from app.risk.models import RiskAccountState, TradePlan
from app.strategy.models import SignalDirection
from app.main import app
from fastapi.testclient import TestClient


NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)


def market_status() -> MarketFeedStatus:
    return MarketFeedStatus(exchange="binance", status=FeedState.CONNECTED, timeframe="1m", symbols={symbol: SymbolFeedStatus(status=FeedState.CONNECTED) for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")})


def candle(minute: int, close: str, high: str | None = None, low: str | None = None) -> Candle:
    opened = NOW + timedelta(minutes=minute)
    price = Decimal(close)
    return Candle(symbol="BTCUSDT", timeframe="1m", open_time=opened, close_time=opened + timedelta(minutes=1) - timedelta(milliseconds=1), open=price, high=Decimal(high or close), low=Decimal(low or close), close=price, volume=Decimal("10"), is_closed=True)


def plan() -> TradePlan:
    return TradePlan(plan_id="plan:restart", source_signal_id="signal:restart", symbol="BTCUSDT", timeframe="1m", direction=SignalDirection.LONG, signal_score=100, signal_confidence=1, entry_reference_price=Decimal("100"), stop_loss_price=Decimal("99"), take_profit_price=Decimal("102"), risk_amount_usdt=Decimal("1"), estimated_quantity=Decimal("1"), approved=True, generated_at=NOW, source_candle_open_time=NOW, source_candle_close_time=NOW + timedelta(minutes=1) - timedelta(milliseconds=1))


def setup(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'forward.db'}")
    database = Database(settings); database.initialize()
    repository = PaperRepository(database)
    session, effective, _ = repository.resume_or_create_session(settings)
    async def sink(_: RiskAccountState): pass
    engine = PaperExecutionEngine(effective, market_status_provider=market_status, risk_account_sink=sink, now_provider=lambda: NOW, repository=repository, session_id=session.session_id)
    return repository, session, effective, engine


def test_sqlite_session_account_position_trade_and_restart_recovery(tmp_path) -> None:
    async def exercise() -> None:
        repository, session, settings, engine = setup(tmp_path)
        assert await engine.process_plan(plan())
        await engine.process_market_candle(candle(1, "100"))
        account, positions, trades = repository.load_state(session.session_id)
        assert account is not None and len(positions) == 1 and trades == []
        restored = PaperExecutionEngine(settings, market_status_provider=market_status, risk_account_sink=lambda _: asyncio.sleep(0), now_provider=lambda: NOW, repository=repository, session_id=session.session_id)
        await restored.restore_state(account, positions, trades)
        assert restored.recovery_status == RecoveryStatus.PENDING
        assert (await restored.positions())[0].status.value == "recovery_pending"
        await restored.reconcile_recovered_positions(lambda *_: asyncio.sleep(0, result=[candle(2, "102", high="102", low="100")]))
        assert restored.recovery_status == RecoveryStatus.COMPLETE
        assert len(await restored.trades(10)) == 1
        recovered_account, recovered_positions, recovered_trades = repository.load_state(session.session_id)
        assert recovered_account is not None and recovered_positions == [] and len(recovered_trades) == 1
        assert repository.metrics(session).closed_trades == 1
    asyncio.run(exercise())


def test_recovery_failure_blocks_new_entries_and_alert_storage_is_idempotent(tmp_path) -> None:
    async def exercise() -> None:
        repository, session, settings, engine = setup(tmp_path)
        assert await engine.process_plan(plan())
        await engine.process_market_candle(candle(1, "100"))
        account, positions, trades = repository.load_state(session.session_id)
        await engine.restore_state(account, positions, trades)
        async def failed_fetch(*_): raise RuntimeError("public history unavailable")
        await engine.reconcile_recovered_positions(failed_fetch)
        assert engine.recovery_status == RecoveryStatus.ERROR
        assert not await engine.process_plan(plan().model_copy(update={"plan_id": "plan:blocked", "source_candle_open_time": NOW + timedelta(minutes=4)}))
        first = repository.upsert_alert(session.session_id, "RECOVERY_ERROR", "critical", "Recovery failed", None, {})
        second = repository.upsert_alert(session.session_id, "RECOVERY_ERROR", "critical", "Recovery failed", None, {})
        assert first.alert_id == second.alert_id and second.count == 2
    asyncio.run(exercise())


def test_active_session_uses_immutable_configuration_snapshot(tmp_path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'snapshot.db'}", ema_fast_period=8, ema_slow_period=20)
    database = Database(settings); database.initialize()
    repository = PaperRepository(database)
    first, effective, resumed = repository.resume_or_create_session(settings)
    second, resumed_settings, resumed = repository.resume_or_create_session(Settings(database_url=settings.database_url, ema_fast_period=9, ema_slow_period=21, starting_balance=200))
    assert resumed
    assert first.session_id == second.session_id
    assert effective.ema_fast_period == resumed_settings.ema_fast_period == 8
    assert resumed_settings.starting_balance == Decimal("100.0")


def test_forward_test_and_system_api_surface() -> None:
    with TestClient(app) as client:
        for path in ("/api/paper/session", "/api/paper/metrics", "/api/paper/metrics/daily", "/api/paper/metrics/equity", "/api/paper/metrics/symbols", "/api/paper/audit", "/api/system/health", "/api/system/database", "/api/system/alerts"):
            assert client.get(path).status_code == 200
        with client.websocket_connect("/ws/market") as websocket:
            assert websocket.receive_json()["type"] == "market.snapshot"
            assert websocket.receive_json()["type"] == "paper.session"
            assert websocket.receive_json()["type"] == "paper.metrics"
            assert websocket.receive_json()["type"] == "system.health"
            assert websocket.receive_json()["type"] == "paper.recovery"
