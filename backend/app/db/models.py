"""Public persistence and forward-monitoring response models."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SessionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class RecoveryStatus(StrEnum):
    COMPLETE = "complete"
    PENDING = "recovery_pending"
    ERROR = "recovery_error"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    ERROR = "error"
    RECOVERY_PENDING = "recovery_pending"
    OFFLINE = "offline"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class PaperSession(BaseModel):
    model_config = ConfigDict(frozen=True)
    session_id: str
    started_at: datetime
    starting_balance: Decimal
    strategy_profile: str
    strategy_config_snapshot: dict[str, object]
    status: SessionStatus


class ForwardMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)
    session_id: str
    elapsed_seconds: int
    signals: int = 0
    actionable_signals: int = 0
    risk_approvals: int = 0
    risk_rejections: int = 0
    paper_entries: int = 0
    closed_trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_pnl: Decimal = Decimal(0)
    net_pnl: Decimal = Decimal(0)
    fees: Decimal = Decimal(0)
    win_rate: Decimal | None = None
    profit_factor: Decimal | None = None
    expectancy_per_trade: Decimal | None = None
    average_r_multiple: Decimal | None = None
    max_drawdown_percent: Decimal = Decimal(0)
    current_drawdown_percent: Decimal = Decimal(0)
    current_equity: Decimal = Decimal(0)


class DailyMetric(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: date
    starting_equity: Decimal
    ending_equity: Decimal
    trades: int
    wins: int
    losses: int
    net_pnl: Decimal
    fees: Decimal
    max_drawdown_percent: Decimal
    daily_return_percent: Decimal


class SymbolMetric(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    trades: int
    wins: int
    net_pnl: Decimal
    win_rate: Decimal | None
    profit_factor: Decimal | None
    average_r_multiple: Decimal | None


class AlertEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    alert_id: str
    code: str
    severity: AlertSeverity
    message: str
    symbol: str | None = None
    created_at: datetime
    first_seen: datetime
    last_seen: datetime
    count: int = 1
    resolved_at: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SystemHealth(BaseModel):
    model_config = ConfigDict(frozen=True)
    overall: HealthStatus
    database: HealthStatus
    market: HealthStatus
    indicators: HealthStatus
    strategy: HealthStatus
    risk: HealthStatus
    paper_execution: HealthStatus
    recovery: RecoveryStatus
    freshness: dict[str, datetime | None] = Field(default_factory=dict)
