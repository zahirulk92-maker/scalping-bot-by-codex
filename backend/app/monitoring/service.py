"""Health aggregation plus deduplicated, persistent internal alerts."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Awaitable, Callable

from app.config import Settings
from app.db.models import AlertEvent, AlertSeverity, HealthStatus, PaperSession, RecoveryStatus, SystemHealth
from app.db.repositories.paper import PaperRepository
from app.execution.paper_engine import PaperExecutionEngine
from app.market.models import FeedState
from app.market.service import MarketDataService

Publisher = Callable[[dict[str, object]], Awaitable[None]]


class MonitoringService:
    def __init__(self, settings: Settings, repository: PaperRepository, session: PaperSession, market: MarketDataService, paper: PaperExecutionEngine, publish: Publisher | None = None) -> None:
        self.settings = settings
        self.repository = repository
        self.session = session
        self.market = market
        self.paper = paper
        self.publish = publish
        self.freshness: dict[str, datetime | None] = {key: None for key in ("last_market_update", "last_closed_candle", "last_indicator_snapshot", "last_strategy_signal", "last_risk_plan", "last_paper_event", "last_database_write")}
        self._last_alert_emit: dict[tuple[str, str | None], datetime] = {}
        self.counters: dict[str, int] = {"signals_generated": 0, "risk_plans": 0, "paper_entries": 0, "paper_closes": 0, "db_errors": 0}

    async def record_event(self, event_type: str, data: dict[str, object]) -> None:
        now = datetime.now(UTC)
        key = "last_paper_event" if event_type.startswith("paper.") else "last_strategy_signal" if event_type == "strategy.signal" else "last_risk_plan" if event_type == "risk.plan" else None
        if key:
            self.freshness[key] = now
        counter = {"strategy.signal": "signals_generated", "risk.plan": "risk_plans", "paper.position_opened": "paper_entries", "paper.position_closed": "paper_closes"}.get(event_type)
        if counter:
            self.counters[counter] += 1
        if event_type == "market.candle":
            self.freshness["last_market_update"] = now
            if data.get("is_closed"):
                self.freshness["last_closed_candle"] = now
        if event_type == "indicator.snapshot":
            self.freshness["last_indicator_snapshot"] = now
        if event_type == "market.status":
            state = str(data.get("status", ""))
            if state in {"stale", "disconnected", "error"}:
                await self.alert("MARKET_STALE", AlertSeverity.WARNING, f"Public market feed is {state}")
            else:
                await self.resolve("MARKET_STALE")
        if event_type == "paper.recovery":
            state = str(data.get("status", ""))
            if state == RecoveryStatus.ERROR.value:
                await self.alert("RECOVERY_ERROR", AlertSeverity.CRITICAL, "Paper recovery failed; new entries are blocked")
            elif state == RecoveryStatus.COMPLETE.value:
                await self.resolve("RECOVERY_ERROR")
        if event_type == "paper.account_updated":
            pnl = Decimal(str(data.get("realized_pnl_today", "0")))
            if pnl <= Decimal(str(-self.settings.starting_balance * self.settings.max_daily_loss)):
                await self.alert("DAILY_LOSS_LIMIT_REACHED", AlertSeverity.WARNING, "Paper daily loss limit is reached")
        if event_type in {"paper.position_opened", "paper.position_closed", "strategy.signal", "risk.plan"}:
            self.repository.persist_audit(self.session.session_id, event_type, data, str(data.get("position_id") or data.get("trade_id") or data.get("signal_id") or data.get("plan_id") or ""))
            self.freshness["last_database_write"] = now

    async def alert(self, code: str, severity: AlertSeverity, message: str, symbol: str | None = None, metadata: dict[str, object] | None = None) -> AlertEvent | None:
        now = datetime.now(UTC)
        identity = (code, symbol)
        previous = self._last_alert_emit.get(identity)
        event = self.repository.upsert_alert(self.session.session_id, code, severity.value, message, symbol, metadata or {})
        if previous and now - previous < timedelta(seconds=self.settings.alert_cooldown_seconds):
            return None
        self._last_alert_emit[identity] = now
        if self.publish:
            await self.publish({"type": "paper.warning", "data": event.model_dump(mode="json")})
        return event

    async def resolve(self, code: str, symbol: str | None = None) -> AlertEvent | None:
        event = self.repository.resolve_alert(self.session.session_id, code, symbol)
        if event and self.publish:
            await self.publish({"type": "paper.warning", "data": event.model_dump(mode="json")})
        return event

    def health(self) -> SystemHealth:
        database = HealthStatus.HEALTHY
        try:
            self.repository.database_status()
        except Exception:
            database = HealthStatus.ERROR
        market_state = self.market.status_snapshot().status
        market = HealthStatus.HEALTHY if market_state == FeedState.CONNECTED else HealthStatus.STALE if market_state == FeedState.STALE else HealthStatus.OFFLINE if market_state == FeedState.DISCONNECTED else HealthStatus.DEGRADED
        recovery = self.paper.recovery_status
        overall = HealthStatus.ERROR if database == HealthStatus.ERROR or recovery == RecoveryStatus.ERROR else HealthStatus.DEGRADED if market != HealthStatus.HEALTHY or recovery == RecoveryStatus.PENDING else HealthStatus.HEALTHY
        return SystemHealth(overall=overall, database=database, market=market, indicators=HealthStatus.HEALTHY if self.freshness["last_indicator_snapshot"] else HealthStatus.DEGRADED, strategy=HealthStatus.HEALTHY if self.freshness["last_strategy_signal"] else HealthStatus.DEGRADED, risk=HealthStatus.HEALTHY if self.freshness["last_risk_plan"] else HealthStatus.DEGRADED, paper_execution=HealthStatus.HEALTHY if recovery == RecoveryStatus.COMPLETE else HealthStatus.DEGRADED, recovery=recovery, freshness=self.freshness)
