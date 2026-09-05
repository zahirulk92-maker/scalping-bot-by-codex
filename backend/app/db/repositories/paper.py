"""Durable PAPER session repository with idempotent lifecycle writes."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.config import Settings
from app.db.database import Database
from app.db.models import AlertEvent, DailyMetric, ForwardMetrics, PaperSession, SessionStatus, SymbolMetric
from app.execution.models import ClosedPaperTrade, PaperAccount, PaperPosition
from app.risk.models import TradePlan
from app.strategy.models import SignalSnapshot


def _dump(model: object) -> str:
    return json.dumps(model.model_dump(mode="json"), separators=(",", ":"))  # type: ignore[attr-defined]


class PaperRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def database_status(self) -> dict[str, object]:
        with self.database.connection() as connection:
            version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] or 0
        return {"status": "healthy", "schema_version": int(version)}

    def prune_resolved_alerts(self, retention_days: int) -> int:
        """Keep active alerts indefinitely while bounding old resolved-alert history."""
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        with self.database.transaction() as connection:
            result = connection.execute("DELETE FROM alerts WHERE resolved_at IS NOT NULL AND resolved_at < ?", (cutoff,))
        return int(result.rowcount)

    def resume_or_create_session(self, settings: Settings) -> tuple[PaperSession, Settings, bool]:
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM paper_sessions WHERE status = ? ORDER BY started_at DESC LIMIT 1", (SessionStatus.ACTIVE.value,)).fetchone()
            if row:
                snapshot = json.loads(row["config_snapshot"])
                session = PaperSession(session_id=row["session_id"], started_at=datetime.fromisoformat(row["started_at"]), starting_balance=Decimal(row["starting_balance"]), strategy_profile=row["strategy_profile"], strategy_config_snapshot=snapshot, status=SessionStatus(row["status"]))
                return session, Settings(**snapshot), True
            effective = settings.effective_strategy_settings()
            now = datetime.now(UTC)
            session = PaperSession(session_id=f"session:{uuid4()}", started_at=now, starting_balance=Decimal(str(effective.starting_balance)), strategy_profile=effective.strategy_profile, strategy_config_snapshot=effective.model_dump(mode="json"), status=SessionStatus.ACTIVE)
            connection.execute("INSERT INTO paper_sessions VALUES (?, ?, ?, ?, ?, ?)", (session.session_id, now.isoformat(), str(session.starting_balance), session.strategy_profile, json.dumps(session.strategy_config_snapshot, separators=(",", ":")), session.status.value))
            return session, effective, False

    def load_state(self, session_id: str) -> tuple[PaperAccount | None, list[PaperPosition], list[ClosedPaperTrade]]:
        with self.database.connection() as connection:
            account_row = connection.execute("SELECT data FROM paper_accounts WHERE session_id = ?", (session_id,)).fetchone()
            positions = connection.execute("SELECT data FROM paper_positions WHERE session_id = ?", (session_id,)).fetchall()
            trades = connection.execute("SELECT data FROM paper_trades WHERE session_id = ? ORDER BY closed_at", (session_id,)).fetchall()
        return (PaperAccount.model_validate(json.loads(account_row["data"])) if account_row else None, [PaperPosition.model_validate(json.loads(row["data"])) for row in positions], [ClosedPaperTrade.model_validate(json.loads(row["data"])) for row in trades])

    def validation_snapshots(self, session_id: str, limit: int, offset: int = 0) -> list[dict[str, object]]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT data FROM validation_snapshots WHERE session_id = ? ORDER BY evaluated_at DESC LIMIT ? OFFSET ?", (session_id, limit, offset)).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def persist_validation_snapshot(self, session_id: str, snapshot_id: str, evaluated_at: datetime, status: str, data: dict[str, object]) -> None:
        with self.database.transaction() as connection:
            connection.execute("INSERT INTO validation_snapshots(snapshot_id, session_id, evaluated_at, status, data) VALUES (?, ?, ?, ?, ?)", (snapshot_id, session_id, evaluated_at.isoformat(), status, json.dumps(data, separators=(",", ":"))))

    def persist_open(self, session_id: str, account: PaperAccount, position: PaperPosition) -> None:
        with self.database.transaction() as connection:
            self._upsert_account(connection, session_id, account)
            self._upsert_position(connection, session_id, position)
            self._upsert_daily(connection, session_id, account)

    def persist_close(self, session_id: str, account: PaperAccount, trade: ClosedPaperTrade) -> None:
        with self.database.transaction() as connection:
            self._upsert_account(connection, session_id, account)
            connection.execute("DELETE FROM paper_positions WHERE position_id = ?", (trade.position_id,))
            connection.execute("INSERT OR IGNORE INTO paper_trades(trade_id, session_id, position_id, closed_at, data) VALUES (?, ?, ?, ?, ?)", (trade.trade_id, session_id, trade.position_id, trade.closed_at.isoformat(), _dump(trade)))
            self._upsert_daily(connection, session_id, account)

    def persist_account(self, session_id: str, account: PaperAccount) -> None:
        with self.database.transaction() as connection:
            self._upsert_account(connection, session_id, account)
            self._upsert_daily(connection, session_id, account)

    def persist_signal(self, session_id: str, signal: SignalSnapshot) -> None:
        if not signal.signal_id:
            return
        with self.database.transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO signal_snapshots(signal_id, session_id, generated_at, data) VALUES (?, ?, ?, ?)", (signal.signal_id, session_id, (signal.generated_at or datetime.now(UTC)).isoformat(), _dump(signal)))

    def persist_plan(self, session_id: str, plan: TradePlan) -> None:
        if not plan.plan_id:
            return
        with self.database.transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO risk_plans(plan_id, session_id, generated_at, approved, data) VALUES (?, ?, ?, ?, ?)", (plan.plan_id, session_id, (plan.generated_at or datetime.now(UTC)).isoformat(), int(plan.approved), _dump(plan)))

    def persist_audit(self, session_id: str, event_type: str, data: dict[str, object], event_id: str | None = None) -> None:
        now = datetime.now(UTC)
        identity = event_id or f"audit:{event_type}:{uuid4()}"
        with self.database.transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO audit_events VALUES (?, ?, ?, ?, ?)", (identity, session_id, event_type, now.isoformat(), json.dumps(data, separators=(",", ":"))))

    def metrics(self, session: PaperSession) -> ForwardMetrics:
        account, _, trades = self.load_state(session.session_id)
        with self.database.connection() as connection:
            signals = connection.execute("SELECT COUNT(*) FROM signal_snapshots WHERE session_id = ?", (session.session_id,)).fetchone()[0]
            actionable = connection.execute("SELECT COUNT(*) FROM signal_snapshots WHERE session_id = ? AND json_extract(data, '$.is_actionable') = 1", (session.session_id,)).fetchone()[0]
            approvals = connection.execute("SELECT COUNT(*) FROM risk_plans WHERE session_id = ? AND approved = 1", (session.session_id,)).fetchone()[0]
            rejections = connection.execute("SELECT COUNT(*) FROM risk_plans WHERE session_id = ? AND approved = 0", (session.session_id,)).fetchone()[0]
            entries = connection.execute("SELECT COUNT(*) FROM audit_events WHERE session_id = ? AND event_type = 'paper.position_opened'", (session.session_id,)).fetchone()[0]
            points = [Decimal(row[0]) for row in connection.execute("SELECT equity FROM equity_points WHERE session_id = ? ORDER BY timestamp", (session.session_id,))]
        wins = [trade for trade in trades if trade.net_pnl_usdt > 0]
        losses = [trade for trade in trades if trade.net_pnl_usdt < 0]
        gross_wins = sum((trade.net_pnl_usdt for trade in wins), Decimal(0))
        gross_losses = sum((trade.net_pnl_usdt for trade in losses), Decimal(0))
        r_values = [trade.net_pnl_usdt / trade.risk_amount_usdt for trade in trades if trade.risk_amount_usdt and trade.risk_amount_usdt > 0]
        peak = max(points, default=session.starting_balance)
        equity = account.equity if account else session.starting_balance
        max_drawdown = max(((peak - point) / peak * Decimal(100) for point in points if peak), default=Decimal(0))
        return ForwardMetrics(session_id=session.session_id, elapsed_seconds=max(0, int((datetime.now(UTC) - session.started_at).total_seconds())), signals=signals, actionable_signals=actionable, risk_approvals=approvals, risk_rejections=rejections, paper_entries=entries, closed_trades=len(trades), wins=len(wins), losses=len(losses), gross_pnl=sum((trade.gross_pnl_usdt for trade in trades), Decimal(0)), net_pnl=sum((trade.net_pnl_usdt for trade in trades), Decimal(0)), fees=sum((trade.fees_usdt for trade in trades), Decimal(0)), win_rate=Decimal(len(wins)) / len(trades) if trades else None, profit_factor=gross_wins / abs(gross_losses) if gross_losses else None, expectancy_per_trade=sum((trade.net_pnl_usdt for trade in trades), Decimal(0)) / len(trades) if trades else None, average_r_multiple=sum(r_values, Decimal(0)) / len(r_values) if r_values else None, max_drawdown_percent=max_drawdown, current_drawdown_percent=(peak - equity) / peak * Decimal(100) if peak else Decimal(0), current_equity=equity)

    def daily_metrics(self, session_id: str, limit: int) -> list[DailyMetric]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT data FROM daily_metrics WHERE session_id = ? ORDER BY metric_date DESC LIMIT ?", (session_id, limit)).fetchall()
        return [DailyMetric.model_validate(json.loads(row["data"])) for row in rows]

    def equity_curve(self, session_id: str, limit: int) -> list[dict[str, str]]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT timestamp, equity FROM equity_points WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?", (session_id, limit)).fetchall()
        return [{"timestamp": row["timestamp"], "equity": row["equity"]} for row in reversed(rows)]

    def symbol_metrics(self, session_id: str, symbols: list[str]) -> list[SymbolMetric]:
        _, _, trades = self.load_state(session_id)
        values = []
        for symbol in symbols:
            subset = [trade for trade in trades if trade.symbol == symbol]
            wins = [trade for trade in subset if trade.net_pnl_usdt > 0]
            losses = [trade for trade in subset if trade.net_pnl_usdt < 0]
            profit = sum((trade.net_pnl_usdt for trade in wins), Decimal(0))
            loss = sum((trade.net_pnl_usdt for trade in losses), Decimal(0))
            r_values = [trade.net_pnl_usdt / trade.risk_amount_usdt for trade in subset if trade.risk_amount_usdt and trade.risk_amount_usdt > 0]
            values.append(SymbolMetric(symbol=symbol, trades=len(subset), wins=len(wins), net_pnl=sum((trade.net_pnl_usdt for trade in subset), Decimal(0)), win_rate=Decimal(len(wins)) / len(subset) if subset else None, profit_factor=profit / abs(loss) if loss else None, average_r_multiple=sum(r_values, Decimal(0)) / len(r_values) if r_values else None))
        return values

    def audit(self, session_id: str, limit: int, offset: int) -> list[dict[str, object]]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT event_id, event_type, created_at, data FROM audit_events WHERE session_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?", (session_id, limit, offset)).fetchall()
        return [{"event_id": row["event_id"], "event_type": row["event_type"], "created_at": row["created_at"], "data": json.loads(row["data"])} for row in rows]

    def active_alerts(self, session_id: str) -> list[AlertEvent]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM alerts WHERE session_id = ? AND resolved_at IS NULL ORDER BY last_seen DESC", (session_id,)).fetchall()
        return [self._alert_from_row(row) for row in rows]

    def upsert_alert(self, session_id: str, code: str, severity: str, message: str, symbol: str | None, metadata: dict[str, object]) -> AlertEvent:
        now = datetime.now(UTC)
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM alerts WHERE session_id = ? AND code = ? AND symbol IS ?", (session_id, code, symbol)).fetchone()
            if row:
                connection.execute("UPDATE alerts SET last_seen = ?, alert_count = ?, severity = ?, message = ?, metadata = ?, resolved_at = NULL WHERE alert_id = ?", (now.isoformat(), row["alert_count"] + 1, severity, message, json.dumps(metadata), row["alert_id"]))
                row = connection.execute("SELECT * FROM alerts WHERE alert_id = ?", (row["alert_id"],)).fetchone()
            else:
                identity = f"alert:{uuid4()}"
                connection.execute("INSERT INTO alerts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (identity, session_id, code, symbol, severity, message, now.isoformat(), now.isoformat(), 1, None, json.dumps(metadata)))
                row = connection.execute("SELECT * FROM alerts WHERE alert_id = ?", (identity,)).fetchone()
        return self._alert_from_row(row)

    def resolve_alert(self, session_id: str, code: str, symbol: str | None = None) -> AlertEvent | None:
        now = datetime.now(UTC)
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM alerts WHERE session_id = ? AND code = ? AND symbol IS ? AND resolved_at IS NULL", (session_id, code, symbol)).fetchone()
            if not row:
                return None
            connection.execute("UPDATE alerts SET resolved_at = ?, last_seen = ? WHERE alert_id = ?", (now.isoformat(), now.isoformat(), row["alert_id"]))
            row = connection.execute("SELECT * FROM alerts WHERE alert_id = ?", (row["alert_id"],)).fetchone()
        return self._alert_from_row(row)

    def _upsert_account(self, connection, session_id: str, account: PaperAccount) -> None:
        now = datetime.now(UTC)
        connection.execute("INSERT INTO paper_accounts VALUES (?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at", (session_id, _dump(account), now.isoformat()))
        connection.execute("INSERT OR REPLACE INTO equity_points VALUES (?, ?, ?)", (session_id, now.isoformat(), str(account.equity)))

    def _upsert_position(self, connection, session_id: str, position: PaperPosition) -> None:
        connection.execute("INSERT INTO paper_positions VALUES (?, ?, ?, ?, ?) ON CONFLICT(position_id) DO UPDATE SET status=excluded.status, data=excluded.data, updated_at=excluded.updated_at", (position.position_id, session_id, position.status.value, _dump(position), datetime.now(UTC).isoformat()))

    def _upsert_daily(self, connection, session_id: str, account: PaperAccount) -> None:
        day = account.statistics_day
        rows = connection.execute("SELECT data FROM paper_trades WHERE session_id = ?", (session_id,)).fetchall()
        trades = [ClosedPaperTrade.model_validate(json.loads(row["data"])) for row in rows if ClosedPaperTrade.model_validate(json.loads(row["data"])).closed_at.date() == day]
        wins = [trade for trade in trades if trade.net_pnl_usdt > 0]
        losses = [trade for trade in trades if trade.net_pnl_usdt < 0]
        start = account.starting_balance + account.realized_pnl - sum((trade.net_pnl_usdt for trade in trades), Decimal(0))
        metric = DailyMetric(date=day, starting_equity=start, ending_equity=account.equity, trades=len(trades), wins=len(wins), losses=len(losses), net_pnl=sum((trade.net_pnl_usdt for trade in trades), Decimal(0)), fees=sum((trade.fees_usdt for trade in trades), Decimal(0)), max_drawdown_percent=Decimal(0), daily_return_percent=(account.equity - start) / start * Decimal(100) if start else Decimal(0))
        connection.execute("INSERT OR REPLACE INTO daily_metrics VALUES (?, ?, ?)", (session_id, day.isoformat(), _dump(metric)))

    @staticmethod
    def _alert_from_row(row) -> AlertEvent:
        return AlertEvent(alert_id=row["alert_id"], code=row["code"], severity=row["severity"], message=row["message"], symbol=row["symbol"], created_at=datetime.fromisoformat(row["first_seen"]), first_seen=datetime.fromisoformat(row["first_seen"]), last_seen=datetime.fromisoformat(row["last_seen"]), count=row["alert_count"], resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None, metadata=json.loads(row["metadata"]))
