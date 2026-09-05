"""Explainable, fail-closed validation for durable paper-forward results."""

import asyncio
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Awaitable, Callable
from uuid import uuid4

from app.backtest.engine import BacktestEngine
from app.config import Settings
from app.db.models import HealthStatus, PaperSession, RecoveryStatus, SessionStatus
from app.db.repositories.paper import PaperRepository
from app.execution.models import ClosedPaperTrade
from app.execution.paper_engine import PaperExecutionEngine
from app.monitoring.service import MonitoringService
from app.strategy.models import SignalDirection
from app.validation.models import RuleResult, RuleStatus, ValidationSnapshot, ValidationStatus
from app.validation.rules import maximum_losing_streak, trade_metrics
from app.validation.store import ValidationStore

Publisher = Callable[[dict[str, object]], Awaitable[None]]


class ValidationEngine:
    """Evaluates all closed trades in the immutable active paper session."""

    def __init__(self, settings: Settings, runtime_settings: Settings, repository: PaperRepository, session: PaperSession, paper: PaperExecutionEngine, monitoring: MonitoringService, backtests: BacktestEngine, publish: Publisher) -> None:
        self.settings = settings
        self.runtime_settings = runtime_settings
        self.repository = repository
        self.session = session
        self.paper = paper
        self.monitoring = monitoring
        self.backtests = backtests
        self.publish = publish
        self.store = ValidationStore(repository)
        self.current = self.store.latest(session.session_id)
        self._lock = asyncio.Lock()

    @staticmethod
    def _rule(rule_id: str, name: str, status: RuleStatus, actual: object, required: object, message: str, hard: bool = False) -> RuleResult:
        return RuleResult(rule_id=rule_id, name=name, status=status, actual_value=actual, required_value=required, message=message, hard=hard)

    async def evaluate(self, trigger: str = "periodic") -> ValidationSnapshot:
        async with self._lock:
            snapshot = self._evaluate(trigger)
            previous = self.current.status if self.current else None
            snapshot = snapshot.model_copy(update={"transition_from": previous})
            self.store.save(snapshot)
            self.current = snapshot
            if snapshot.status == ValidationStatus.FAIL and self.settings.pause_paper_on_validation_fail:
                self.paper.set_entries_paused(True)
            elif snapshot.status == ValidationStatus.PASS:
                self.paper.set_entries_paused(False)
        payload = snapshot.model_dump(mode="json")
        await self.publish({"type": "validation.updated", "data": payload})
        if snapshot.status == ValidationStatus.FAIL:
            await self.publish({"type": "validation.failed", "data": payload})
        elif snapshot.status == ValidationStatus.PASS:
            await self.publish({"type": "validation.passed", "data": payload})
        for warning in snapshot.warnings:
            await self.publish({"type": "validation.warning", "data": {"code": warning, "snapshot_id": snapshot.snapshot_id}})
        return snapshot

    def _evaluate(self, trigger: str) -> ValidationSnapshot:
        _, _, trades = self.repository.load_state(self.session.session_id)
        trades = sorted(trades, key=lambda value: value.closed_at)
        metrics = trade_metrics(trades, self.session.starting_balance)
        session_days = max(0, (datetime.now(UTC).date() - self.session.started_at.date()).days)
        rules: list[RuleResult] = []
        warnings: list[str] = []

        health = self.monitoring.health()
        active_alerts = self.repository.active_alerts(self.session.session_id)
        critical_alerts = [item.code for item in active_alerts if item.code in {"RECOVERY_ERROR", "DATABASE_ERROR", "DUPLICATE_LIFECYCLE_ERROR"}]
        health_ok = health.overall != HealthStatus.ERROR and health.recovery != RecoveryStatus.ERROR and not critical_alerts
        rules.append(self._rule("operational_health", "Operational health", RuleStatus.PASS if health_ok else RuleStatus.FAIL, health.overall.value, "no error / recovery failure", "Operational components are acceptable" if health_ok else "A critical operational or recovery issue prevents validation PASS", True))
        data_quality = "healthy" if health_ok else "critical_issue"
        if any(item.code == "MARKET_STALE" for item in active_alerts):
            warnings.append("DATA_QUALITY_ISSUE")
            data_quality = "warning"
            rules.append(self._rule("market_data_quality", "Market data quality", RuleStatus.WARNING, "market stale alert active", "no unresolved stale alert", "Public market freshness needs review"))

        session_paused = self.session.status == SessionStatus.PAUSED
        rules.append(self._rule("session_paused", "Session pause state", RuleStatus.WARNING if session_paused else RuleStatus.PASS, self.session.status.value, "active", "Session is manually paused" if session_paused else "Session is active"))
        sample_ok = len(trades) >= self.settings.min_forward_trades and session_days >= self.settings.min_forward_days
        rules.append(self._rule("minimum_sample", "Minimum forward sample", RuleStatus.PASS if sample_ok else RuleStatus.NOT_ENOUGH_DATA, {"closed_trades": len(trades), "forward_days": session_days}, {"closed_trades": self.settings.min_forward_trades, "forward_days": self.settings.min_forward_days}, "Minimum chronological forward sample met" if sample_ok else "More closed trades and/or elapsed forward days are required", True))

        if sample_ok:
            average_r = metrics["expectancy_r"]
            net_expectancy = metrics["expectancy_net"]
            expectancy_ok = isinstance(average_r, Decimal) and isinstance(net_expectancy, Decimal) and average_r >= Decimal(str(self.settings.min_forward_expectancy_r)) and net_expectancy > 0
            rules.append(self._rule("expectancy", "Net expectancy after costs", RuleStatus.PASS if expectancy_ok else RuleStatus.FAIL, {"expectancy_r": average_r, "net_expectancy": net_expectancy}, {"min_expectancy_r": self.settings.min_forward_expectancy_r, "net_expectancy": "> 0"}, "Net expectancy clears the acceptance threshold" if expectancy_ok else "Net expectancy after fees/slippage is below acceptance", True))
            pf = metrics["profit_factor"]
            net_pnl = metrics["net_pnl"]
            pf_ok = (pf is None and isinstance(net_pnl, Decimal) and net_pnl > 0) or (isinstance(pf, Decimal) and pf >= Decimal(str(self.settings.min_forward_profit_factor)))
            rules.append(self._rule("profit_factor", "Profit factor", RuleStatus.PASS if pf_ok else RuleStatus.FAIL, pf if pf is not None else "no losing trades", self.settings.min_forward_profit_factor, "Profit factor is acceptable" if pf_ok else "Profit factor is below the operational threshold", True))
            drawdown = metrics["max_drawdown_percent"]
            drawdown_ok = isinstance(drawdown, Decimal) and drawdown <= Decimal(str(self.settings.max_forward_drawdown_percent))
            rules.append(self._rule("drawdown", "Maximum drawdown", RuleStatus.PASS if drawdown_ok else RuleStatus.FAIL, drawdown, self.settings.max_forward_drawdown_percent, "Drawdown is within the configured limit" if drawdown_ok else "Forward drawdown exceeded the configured limit", True))
            streak = maximum_losing_streak(trades)
            streak_ok = streak <= self.settings.max_consecutive_losses
            rules.append(self._rule("losing_streak", "Consecutive losses", RuleStatus.PASS if streak_ok else RuleStatus.FAIL, streak, self.settings.max_consecutive_losses, "Losing streak is within limit" if streak_ok else "Maximum losing streak exceeded the configured limit", True))
            lock_events = self._daily_lock_events(trades)
            lock_ok = lock_events <= self.settings.max_daily_lock_events
            rules.append(self._rule("daily_loss_locks", "Daily loss lock events", RuleStatus.PASS if lock_ok else RuleStatus.FAIL, lock_events, self.settings.max_daily_lock_events, "Daily loss locks are within limit" if lock_ok else "Too many UTC daily-loss lock events", True))
            self._append_symbol_rules(trades, rules)
        else:
            for rule_id, name in (("expectancy", "Net expectancy after costs"), ("profit_factor", "Profit factor"), ("drawdown", "Maximum drawdown"), ("losing_streak", "Consecutive losses"), ("daily_loss_locks", "Daily loss lock events"), ("symbol_coverage", "Healthy symbol coverage")):
                rules.append(self._rule(rule_id, name, RuleStatus.NOT_ENOUGH_DATA, None, "minimum sample", "Deferred until the minimum forward sample is met", rule_id not in {"symbol_coverage"}))

        self._append_cost_and_history_rules(trades, metrics, session_days, rules, warnings)
        self._append_direction_and_rolling_rules(trades, metrics, session_days, rules, warnings)
        config_match = self._config_matches_session()
        if not config_match:
            warnings.append("CONFIG_MISMATCH")
        rules.append(self._rule("config_consistency", "Immutable session configuration", RuleStatus.PASS if config_match else RuleStatus.WARNING, self.runtime_settings.strategy_profile, self.session.strategy_profile, "Runtime profile matches the frozen session snapshot" if config_match else "Runtime strategy settings differ from the immutable active session", False))

        hard_failures = [item.message for item in rules if item.hard and item.status == RuleStatus.FAIL]
        if session_paused:
            status = ValidationStatus.PAUSED
        elif not health_ok:
            status = ValidationStatus.FAIL
        elif not sample_ok:
            status = ValidationStatus.INSUFFICIENT_DATA
        elif hard_failures:
            status = ValidationStatus.FAIL
        else:
            status = ValidationStatus.PASS
        reasons = tuple(item.message for item in rules if item.status == RuleStatus.FAIL)
        return ValidationSnapshot(snapshot_id=f"validation:{uuid4()}", status=status, evaluated_at=datetime.now(UTC), session_id=self.session.session_id, reasons=reasons, warnings=tuple(dict.fromkeys(warnings)), metrics_snapshot={**metrics, "forward_days": session_days, "preferred_sample": {"trades": self.settings.preferred_forward_trades, "days": self.settings.preferred_forward_days}, "trigger": trigger, "rolling_7d": self._window_metrics(trades, self.settings.validation_short_window_days), "rolling_30d": self._window_metrics(trades, self.settings.validation_long_window_days) if session_days >= self.settings.validation_long_window_days else None}, rule_results=tuple(rules), data_quality_status=data_quality)

    def _daily_lock_events(self, trades: list[ClosedPaperTrade]) -> int:
        daily: defaultdict[object, Decimal] = defaultdict(Decimal)
        for trade in trades:
            daily[trade.closed_at.date()] += trade.net_pnl_usdt
        threshold = -self.session.starting_balance * Decimal(str(self.settings.max_daily_loss))
        return sum(1 for pnl in daily.values() if pnl <= threshold)

    def _append_symbol_rules(self, trades: list[ClosedPaperTrade], rules: list[RuleResult]) -> None:
        healthy = 0
        summary: dict[str, object] = {}
        for symbol in self.settings.symbols:
            values = trade_metrics([trade for trade in trades if trade.symbol == symbol], self.session.starting_balance)
            trade_count = values["trades"]
            enough = isinstance(trade_count, int) and trade_count >= self.settings.min_forward_trades_per_symbol
            expectation = values["expectancy_r"]
            profit_factor = values["profit_factor"]
            acceptable = enough and isinstance(expectation, Decimal) and expectation > 0 and (profit_factor is None or isinstance(profit_factor, Decimal) and profit_factor >= Decimal(str(self.settings.min_forward_profit_factor)))
            healthy += int(acceptable)
            summary[symbol] = {"trades": values["trades"], "expectancy_r": expectation, "profit_factor": profit_factor, "healthy": acceptable, "enough_data": enough}
        rules.append(self._rule("symbol_coverage", "Healthy symbol coverage", RuleStatus.PASS if healthy >= self.settings.min_healthy_symbols else RuleStatus.FAIL, summary, self.settings.min_healthy_symbols, "Enough symbols have independent acceptable forward results" if healthy >= self.settings.min_healthy_symbols else "Too few symbols meet the symbol-level acceptance criteria", True))

    def _append_cost_and_history_rules(self, trades: list[ClosedPaperTrade], metrics: dict[str, object], session_days: int, rules: list[RuleResult], warnings: list[str]) -> None:
        costs = metrics["fees"]
        gross_profit = metrics["gross_profit"]
        ratio = costs / gross_profit if isinstance(costs, Decimal) and isinstance(gross_profit, Decimal) and gross_profit > 0 else None
        backtest = self.backtests.store.recent()[0] if self.backtests.store.recent() else None
        historical_cost_per_trade = (backtest.total_fees + backtest.total_slippage_cost) / backtest.total_trades if backtest and backtest.total_trades else None
        forward_cost_per_trade = costs / len(trades) if isinstance(costs, Decimal) and trades else None
        degraded = isinstance(ratio, Decimal) and ratio > Decimal(str(self.settings.max_forward_cost_ratio)) or isinstance(historical_cost_per_trade, Decimal) and isinstance(forward_cost_per_trade, Decimal) and forward_cost_per_trade > historical_cost_per_trade * Decimal("1.5")
        if degraded:
            warnings.append("COST_DEGRADATION")
        rules.append(self._rule("cost_sensitivity", "Cost sensitivity", RuleStatus.WARNING if degraded else RuleStatus.PASS, {"fees_per_trade": forward_cost_per_trade, "cost_to_gross_profit": ratio}, {"max_cost_to_gross_profit": self.settings.max_forward_cost_ratio, "historical_cost_per_trade": historical_cost_per_trade}, "Forward costs materially exceed the acceptance reference" if degraded else "Observed cost burden is acceptable"))
        if not backtest:
            warnings.append("HISTORICAL_COMPARISON_UNAVAILABLE")
            rules.append(self._rule("historical_comparison", "Historical validation comparison", RuleStatus.WARNING, None, "latest backtest/optimization validation", "No in-memory historical validation result is available for comparison"))
            return
        historical_expectancy = backtest.average_r_multiple
        forward_expectancy = metrics["expectancy_r"]
        retention = forward_expectancy / historical_expectancy if isinstance(forward_expectancy, Decimal) and historical_expectancy and historical_expectancy > 0 else None
        expectancy_degraded = retention is not None and retention < Decimal(str(self.settings.min_expectancy_retention))
        historical_pf = backtest.profit_factor
        forward_pf = metrics["profit_factor"]
        pf_retention = forward_pf / historical_pf if isinstance(forward_pf, Decimal) and historical_pf and historical_pf > 0 else None
        pf_degraded = pf_retention is not None and pf_retention < Decimal(str(self.settings.min_profit_factor_retention))
        historical_days = max(1, (backtest.end_time.date() - backtest.start_time.date()).days + 1)
        forward_frequency = Decimal(len(trades)) / max(1, session_days)
        historical_frequency = Decimal(backtest.total_trades) / historical_days
        frequency_ratio = forward_frequency / historical_frequency if historical_frequency else None
        frequency_warning = frequency_ratio is not None and (frequency_ratio < Decimal(str(self.settings.min_trade_frequency_retention)) or frequency_ratio > Decimal(str(self.settings.max_trade_frequency_multiple)))
        if expectancy_degraded or pf_degraded or frequency_warning:
            warnings.append("HISTORICAL_DEGRADATION")
        rules.append(self._rule("historical_comparison", "Historical vs forward comparison", RuleStatus.WARNING if expectancy_degraded or pf_degraded or frequency_warning else RuleStatus.PASS, {"expectancy_retention": retention, "profit_factor_retention": pf_retention, "trade_frequency_ratio": frequency_ratio, "historical_win_rate": backtest.win_rate, "forward_win_rate": metrics["win_rate"], "historical_max_drawdown": backtest.max_drawdown_percent, "forward_max_drawdown": metrics["max_drawdown_percent"]}, {"min_expectancy_retention": self.settings.min_expectancy_retention, "min_profit_factor_retention": self.settings.min_profit_factor_retention, "frequency_range": [self.settings.min_trade_frequency_retention, self.settings.max_trade_frequency_multiple]}, "Historical comparison is within configured tolerances" if not (expectancy_degraded or pf_degraded or frequency_warning) else "Forward performance materially deviates from historical validation; review required"))

    def _append_direction_and_rolling_rules(self, trades: list[ClosedPaperTrade], metrics: dict[str, object], session_days: int, rules: list[RuleResult], warnings: list[str]) -> None:
        directions: dict[str, object] = {}
        weak_direction = False
        for direction in (SignalDirection.LONG, SignalDirection.SHORT):
            values = trade_metrics([trade for trade in trades if trade.direction == direction], self.session.starting_balance)
            directions[direction.value] = {"trades": values["trades"], "expectancy_r": values["expectancy_r"], "profit_factor": values["profit_factor"]}
            direction_trades = values["trades"]
            weak_direction = weak_direction or isinstance(direction_trades, int) and direction_trades >= self.settings.min_forward_trades_per_symbol and isinstance(values["expectancy_r"], Decimal) and values["expectancy_r"] <= 0
        if weak_direction:
            warnings.append("DIRECTIONAL_DEPENDENCE")
        rules.append(self._rule("directional_consistency", "Long/short consistency", RuleStatus.WARNING if weak_direction else RuleStatus.PASS, directions, "no established direction with non-positive expectancy", "Directional dependence needs review" if weak_direction else "No established directional dependency"))
        short = self._window_metrics(trades, self.settings.validation_short_window_days)
        long = self._window_metrics(trades, self.settings.validation_long_window_days) if session_days >= self.settings.validation_long_window_days else None
        short_expectancy = short.get("expectancy_r") if short else None
        short_trades = short.get("trades") if short else None
        overall_expectancy = metrics["expectancy_r"]
        decay = isinstance(short_expectancy, Decimal) and isinstance(short_trades, int) and short_trades >= self.settings.min_forward_trades_per_symbol and isinstance(overall_expectancy, Decimal) and overall_expectancy > 0 and short_expectancy < 0
        underwater = metrics["underwater_days"]
        underwater_warning = isinstance(underwater, float) and underwater > self.settings.max_underwater_days
        if decay:
            warnings.append("RECENT_PERFORMANCE_DECAY")
        if underwater_warning:
            warnings.append("TIME_UNDERWATER")
        rules.append(self._rule("rolling_performance", "Rolling performance and equity quality", RuleStatus.WARNING if decay or underwater_warning else RuleStatus.PASS, {"window_7d": short, "window_30d": long, "peak_equity": metrics["peak_equity"], "current_equity": metrics["current_equity"], "underwater_days": underwater}, {"max_underwater_days": self.settings.max_underwater_days}, "Recent performance or time underwater needs review" if decay or underwater_warning else "Rolling performance and equity curve are acceptable"))

    def _window_metrics(self, trades: list[ClosedPaperTrade], days: int) -> dict[str, object]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        return trade_metrics([item for item in trades if item.closed_at >= cutoff], self.session.starting_balance)

    def _config_matches_session(self) -> bool:
        snapshot = self.session.strategy_config_snapshot
        keys = ("strategy_profile", "ema_fast_period", "ema_slow_period", "rsi_long_min", "rsi_long_max", "rsi_short_min", "rsi_short_max", "signal_min_score", "min_vwap_distance_bps", "min_ema_separation_bps", "min_volume_ratio", "min_atr_bps", "max_atr_bps", "atr_stop_multiplier", "target_rr")
        return all(snapshot.get(key) == self.runtime_settings.model_dump(mode="json").get(key) for key in keys)
