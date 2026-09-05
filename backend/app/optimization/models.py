"""Audit-friendly optimization request and result models."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OptimizationRequest(BaseModel):
    symbols: list[str]
    timeframe: str = "1m"
    start_time: datetime
    end_time: datetime
    parameter_grid: dict[str, list[int | float]] = Field(default_factory=dict)
    search_method: Literal["grid"] = "grid"
    train_fraction: float = Field(default=0.60, gt=0, lt=1)
    validation_fraction: float = Field(default=0.20, gt=0, lt=1)
    walk_forward_train_days: int = Field(default=14, gt=0, le=180)
    walk_forward_validation_days: int = Field(default=7, gt=0, le=90)
    walk_forward_step_days: int = Field(default=7, gt=0, le=90)

    @model_validator(mode="after")
    def validate_request(self):
        if not self.symbols:
            raise ValueError("at least one symbol is required")
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if self.train_fraction + self.validation_fraction >= 1:
            raise ValueError("train_fraction + validation_fraction must leave a holdout period")
        if any(not values for values in self.parameter_grid.values()):
            raise ValueError("each parameter grid entry must contain at least one value")
        return self


class EvaluationMetrics(BaseModel):
    total_trades: int
    net_pnl: Decimal
    return_percent: Decimal
    win_rate: Decimal | None
    profit_factor: Decimal | None
    expectancy_per_trade: Decimal | None
    average_r_multiple: Decimal | None
    max_drawdown_usdt: Decimal
    max_drawdown_percent: Decimal
    total_fees: Decimal
    symbol_net_pnl: dict[str, Decimal] = Field(default_factory=dict)


class CostStressResult(BaseModel):
    scenario: Literal["normal", "high", "stress"]
    cost_multiplier: float
    metrics: EvaluationMetrics


class WalkForwardFold(BaseModel):
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    validation_metrics: EvaluationMetrics


class OptimizationCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    candidate_id: str
    is_baseline: bool = False
    parameters: dict[str, int | float] = Field(default_factory=dict)
    train_metrics: EvaluationMetrics
    validation_metrics: EvaluationMetrics
    validation_score: Decimal | None = None
    selection_eligible: bool = False
    warnings: tuple[str, ...] = ()
    stability_score: Decimal | None = None
    cost_stress: tuple[CostStressResult, ...] = ()
    walk_forward: tuple[WalkForwardFold, ...] = ()
    test_metrics: EvaluationMetrics | None = None


class OptimizationRun(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_id: str
    created_at: datetime
    symbols: tuple[str, ...]
    timeframe: str
    start_time: datetime
    end_time: datetime
    train_end: datetime
    validation_end: datetime
    holdout_start: datetime
    baseline: OptimizationCandidate
    candidates: tuple[OptimizationCandidate, ...]
    selected_candidate_id: str | None = None
    selection_reason: str
    invalid_candidates: dict[str, str] = Field(default_factory=dict)
    final_holdout_evaluated: bool = False
