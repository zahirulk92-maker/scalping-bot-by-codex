"""Versioned SQLite schema initialization. Each operation owns its connection."""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import Settings

logger = logging.getLogger(__name__)
SCHEMA_VERSION = 2


class Database:
    def __init__(self, settings: Settings) -> None:
        self.url = settings.database_url
        raw_path = self.url.removeprefix("sqlite:///")
        candidate = Path(raw_path)
        self.path = candidate if candidate.is_absolute() else Path(__file__).resolve().parents[3] / candidate

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.transaction() as connection:
                connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
                applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
                migrations = {1: self._migration_1, 2: self._migration_2}
                for version, migration in migrations.items():
                    if version not in applied:
                        migration(connection)
                        connection.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))", (version,))
            if self.integrity_check() != "ok":
                raise RuntimeError("SQLite integrity check failed")
            logger.info("SQLite initialized at %s; schema version %s", self.path, SCHEMA_VERSION)
        except sqlite3.Error as error:
            logger.exception("SQLite initialization failed for %s", self.path)
            raise RuntimeError("persistent database initialization failed") from error

    def integrity_check(self) -> str:
        with self.connection() as connection:
            return str(connection.execute("PRAGMA quick_check").fetchone()[0])

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _migration_1(connection: sqlite3.Connection) -> None:
        connection.executescript("""
        CREATE TABLE paper_sessions (session_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, starting_balance TEXT NOT NULL, strategy_profile TEXT NOT NULL, config_snapshot TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE paper_accounts (session_id TEXT PRIMARY KEY REFERENCES paper_sessions(session_id), data TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE paper_positions (position_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id), status TEXT NOT NULL, data TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE paper_trades (trade_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id), position_id TEXT NOT NULL, closed_at TEXT NOT NULL, data TEXT NOT NULL);
        CREATE INDEX idx_paper_trades_session_closed ON paper_trades(session_id, closed_at DESC);
        CREATE TABLE signal_snapshots (signal_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id), generated_at TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE risk_plans (plan_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id), generated_at TEXT NOT NULL, approved INTEGER NOT NULL, data TEXT NOT NULL);
        CREATE TABLE equity_points (session_id TEXT NOT NULL REFERENCES paper_sessions(session_id), timestamp TEXT NOT NULL, equity TEXT NOT NULL, PRIMARY KEY(session_id, timestamp));
        CREATE TABLE daily_metrics (session_id TEXT NOT NULL REFERENCES paper_sessions(session_id), metric_date TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(session_id, metric_date));
        CREATE TABLE audit_events (event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id), event_type TEXT NOT NULL, created_at TEXT NOT NULL, data TEXT NOT NULL);
        CREATE INDEX idx_audit_events_session_time ON audit_events(session_id, created_at DESC);
        CREATE TABLE alerts (alert_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id), code TEXT NOT NULL, symbol TEXT, severity TEXT NOT NULL, message TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, alert_count INTEGER NOT NULL, resolved_at TEXT, metadata TEXT NOT NULL, UNIQUE(session_id, code, symbol));
        """)

    @staticmethod
    def _migration_2(connection: sqlite3.Connection) -> None:
        connection.executescript("""
        CREATE TABLE validation_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
            evaluated_at TEXT NOT NULL,
            status TEXT NOT NULL,
            data TEXT NOT NULL
        );
        CREATE INDEX idx_validation_snapshots_session_time ON validation_snapshots(session_id, evaluated_at DESC);
        """)
