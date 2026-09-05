import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.config import Settings
from app.db.database import Database
from app.db.models import HealthStatus, RecoveryStatus, SystemHealth
from app.db.repositories.paper import PaperRepository
from app.execution.models import ClosedPaperTrade, ExitReason, PaperAccount
from app.strategy.models import SignalDirection
from app.validation.engine import ValidationEngine
from app.validation.models import RuleStatus, ValidationStatus


class FakePaper:
    def __init__(self) -> None:
        self.entries_paused = False

    def set_entries_paused(self, paused: bool) -> None:
        self.entries_paused = paused


class FakeMonitoring:
    def __init__(self, overall: HealthStatus = HealthStatus.HEALTHY) -> None:
        self.overall = overall

    def health(self) -> SystemHealth:
        return SystemHealth(overall=self.overall, database=self.overall, market=HealthStatus.HEALTHY, indicators=HealthStatus.HEALTHY, strategy=HealthStatus.HEALTHY, risk=HealthStatus.HEALTHY, paper_execution=HealthStatus.HEALTHY, recovery=RecoveryStatus.COMPLETE)


class FakeStore:
    def recent(self):
        return []


class FakeBacktests:
    store = FakeStore()


def make_trade(index: int, pnl: Decimal, symbol: str = "BTCUSDT", direction: SignalDirection = SignalDirection.LONG) -> ClosedPaperTrade:
    now = datetime.now(UTC) - timedelta(hours=30 - index)
    return ClosedPaperTrade(trade_id=f"trade:{index}", position_id=f"position:{index}", symbol=symbol, direction=direction, entry_fill_price=Decimal("100"), exit_fill_price=Decimal("101"), quantity=Decimal("1"), risk_amount_usdt=Decimal("1"), gross_pnl_usdt=pnl + Decimal("0.01"), fees_usdt=Decimal("0.01"), net_pnl_usdt=pnl, exit_reason=ExitReason.TAKE_PROFIT if pnl > 0 else ExitReason.STOP_LOSS, opened_at=now - timedelta(minutes=5), closed_at=now)


def build_engine(tmp_path, trades: list[ClosedPaperTrade], runtime_overrides: dict[str, object] | None = None, health: HealthStatus = HealthStatus.HEALTHY):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'validation.db'}")
    database = Database(settings)
    database.initialize()
    repository = PaperRepository(database)
    session, effective, _ = repository.resume_or_create_session(settings)
    session = session.model_copy(update={"started_at": datetime.now(UTC) - timedelta(days=8)})
    account = PaperAccount(starting_balance=Decimal("100"), cash_balance=Decimal("100"), equity=Decimal("100"), statistics_day=date.today())
    for trade in trades:
        repository.persist_close(session.session_id, account, trade)
    events: list[dict[str, object]] = []

    async def publish(event: dict[str, object]) -> None:
        events.append(event)

    runtime = Settings(database_url=settings.database_url, **(runtime_overrides or {}))
    paper = FakePaper()
    engine = ValidationEngine(effective, runtime, repository, session, paper, FakeMonitoring(health), FakeBacktests(), publish)
    return engine, paper, repository, events


@pytest.mark.parametrize("count", [0, 10, 29])
def test_validation_requires_minimum_sample(tmp_path, count: int) -> None:
    trades = [make_trade(index, Decimal("0.2"), ["BTCUSDT", "ETHUSDT", "SOLUSDT"][index % 3], SignalDirection.LONG if index % 2 else SignalDirection.SHORT) for index in range(count)]
    engine, paper, _, _ = build_engine(tmp_path, trades)
    snapshot = asyncio.run(engine.evaluate())
    assert snapshot.status == ValidationStatus.INSUFFICIENT_DATA
    assert not paper.entries_paused


def test_validation_passes_with_complete_profitable_symbol_coverage(tmp_path) -> None:
    trades = [make_trade(index, Decimal("0.2"), ["BTCUSDT", "ETHUSDT", "SOLUSDT"][index % 3], SignalDirection.LONG if index % 2 else SignalDirection.SHORT) for index in range(30)]
    engine, paper, repository, events = build_engine(tmp_path, trades)
    snapshot = asyncio.run(engine.evaluate("test"))
    assert snapshot.status == ValidationStatus.PASS
    assert not paper.entries_paused and snapshot.metrics_snapshot["trades"] == 30
    assert repository.validation_snapshots(snapshot.session_id, 5)[0]["status"] == "pass"
    assert any(event["type"] == "validation.passed" for event in events)


def test_losing_streak_failure_pauses_only_new_entries_and_preserves_history(tmp_path) -> None:
    losses = [make_trade(index, Decimal("-1"), ["BTCUSDT", "ETHUSDT", "SOLUSDT"][index % 3]) for index in range(9)]
    wins = [make_trade(index + 9, Decimal("0.5"), ["BTCUSDT", "ETHUSDT", "SOLUSDT"][index % 3], SignalDirection.SHORT) for index in range(21)]
    engine, paper, repository, events = build_engine(tmp_path, losses + wins)
    snapshot = asyncio.run(engine.evaluate())
    streak = next(rule for rule in snapshot.rule_results if rule.rule_id == "losing_streak")
    assert snapshot.status == ValidationStatus.FAIL and streak.status == RuleStatus.FAIL
    assert paper.entries_paused and len(repository.load_state(snapshot.session_id)[2]) == 30
    assert any(event["type"] == "validation.failed" for event in events)


def test_validation_detects_operational_error_and_config_mismatch(tmp_path) -> None:
    trades = [make_trade(index, Decimal("0.2"), ["BTCUSDT", "ETHUSDT", "SOLUSDT"][index % 3]) for index in range(30)]
    engine, _, _, _ = build_engine(tmp_path, trades, {"signal_min_score": 75}, HealthStatus.ERROR)
    snapshot = asyncio.run(engine.evaluate())
    assert snapshot.status == ValidationStatus.FAIL
    assert "CONFIG_MISMATCH" in snapshot.warnings
    assert next(rule for rule in snapshot.rule_results if rule.rule_id == "operational_health").status == RuleStatus.FAIL


def test_validation_configuration_rejects_invalid_window_and_symbol_coverage() -> None:
    with pytest.raises(ValueError, match="validation_long_window_days"):
        Settings(validation_short_window_days=30, validation_long_window_days=7)
    with pytest.raises(ValueError, match="min_healthy_symbols"):
        Settings(min_healthy_symbols=4)
