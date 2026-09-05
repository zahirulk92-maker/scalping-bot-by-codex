"""Public, persisted models for the forward-test validation gate."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ValidationStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INSUFFICIENT_DATA = "insufficient_data"
    PAUSED = "paused"


class RuleStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    NOT_ENOUGH_DATA = "not_enough_data"


class RuleResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str
    name: str
    status: RuleStatus
    actual_value: object | None = None
    required_value: object | None = None
    message: str
    hard: bool = False


class ValidationSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    status: ValidationStatus
    evaluated_at: datetime
    session_id: str
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metrics_snapshot: dict[str, object] = Field(default_factory=dict)
    rule_results: tuple[RuleResult, ...] = ()
    data_quality_status: str = "healthy"
    transition_from: ValidationStatus | None = None
