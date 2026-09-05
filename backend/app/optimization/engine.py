"""Chronological, bounded strategy optimization built on the existing backtester.

The holdout segment is intentionally excluded from all candidate ranking.  It can
only be replayed later through ``final_evaluate`` for the already selected
candidate, never as an input to selection.
"""

import asyncio
import itertools
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal, cast
from uuid import uuid4

from app.backtest.engine import BacktestEngine
from app.backtest.models import BacktestRequest, BacktestResult
from app.config import Settings
from app.market.models import Candle
from app.optimization.models import (
    CostStressResult,
    EvaluationMetrics,
    OptimizationCandidate,
    OptimizationRequest,
    OptimizationRun,
    WalkForwardFold,
)
from app.optimization.store import OptimizationStore


OPTIMIZABLE_FIELDS = {
    "EMA_FAST_PERIOD": "ema_fast_period",
    "EMA_SLOW_PERIOD": "ema_slow_period",
    "RSI_LONG_MIN": "rsi_long_min",
    "RSI_LONG_MAX": "rsi_long_max",
    "RSI_SHORT_MIN": "rsi_short_min",
    "RSI_SHORT_MAX": "rsi_short_max",
    "SIGNAL_MIN_SCORE": "signal_min_score",
    "MIN_VWAP_DISTANCE_BPS": "min_vwap_distance_bps",
    "MIN_EMA_SEPARATION_BPS": "min_ema_separation_bps",
    "MIN_VOLUME_RATIO": "min_volume_ratio",
    "MIN_ATR_BPS": "min_atr_bps",
    "MAX_ATR_BPS": "max_atr_bps",
    "ATR_STOP_MULTIPLIER": "atr_stop_multiplier",
    "TARGET_RR": "target_rr",
}


class OptimizationEngine:
    def __init__(self, settings: Settings, backtest_engine: BacktestEngine | None = None) -> None:
        self.settings = settings
        self.backtest_engine = backtest_engine or BacktestEngine(settings)
        self.store = OptimizationStore(settings.max_optimization_runs)

    async def run(self, request: OptimizationRequest) -> OptimizationRun:
        self._validate(request)
        candle_map = await self._load_once(request)
        train_end, validation_end = self._split_times(request)
        baseline = await self._evaluate_candidate(
            "baseline", True, {}, self.settings, request, candle_map, train_end, validation_end
        )
        candidates: list[OptimizationCandidate] = []
        invalid: dict[str, str] = {}
        for index, parameters in enumerate(self._parameter_combinations(request.parameter_grid), start=1):
            candidate_id = f"candidate-{index:03d}"
            try:
                candidate_settings = self._candidate_settings(parameters)
            except ValueError as error:
                invalid[candidate_id] = str(error)
                continue
            candidates.append(await self._evaluate_candidate(
                candidate_id, False, parameters, candidate_settings, request, candle_map, train_end, validation_end
            ))

        candidates = self._add_stability(candidates)
        eligible = [candidate for candidate in candidates if candidate.selection_eligible]
        selected = max(eligible, key=lambda candidate: candidate.validation_score or Decimal("-1"), default=None)
        if selected:
            selected = await self._research_selected(selected, self._candidate_settings(selected.parameters), request, candle_map)
            candidates = [selected if candidate.candidate_id == selected.candidate_id else candidate for candidate in candidates]
            reason = "Highest validation composite score among candidates that met trade-count, drawdown, and profit-factor gates. Holdout data was not used."
        else:
            reason = "No candidate met the validation eligibility gates; no final holdout evaluation was performed."
        run = OptimizationRun(
            run_id=str(uuid4()), created_at=datetime.now(UTC), symbols=tuple(symbol.upper() for symbol in request.symbols),
            timeframe=request.timeframe, start_time=request.start_time, end_time=request.end_time,
            train_end=train_end, validation_end=validation_end, holdout_start=validation_end,
            baseline=baseline, candidates=tuple(candidates), selected_candidate_id=selected.candidate_id if selected else None,
            selection_reason=reason, invalid_candidates=invalid,
        )
        self.store.save(run)
        return run

    async def final_evaluate(self, run_id: str) -> OptimizationRun:
        run = self.store.get(run_id)
        if run is None:
            raise KeyError(run_id)
        if run.final_holdout_evaluated:
            return run
        if not run.selected_candidate_id:
            raise ValueError("no eligible candidate was selected for final holdout evaluation")
        selected = next(candidate for candidate in run.candidates if candidate.candidate_id == run.selected_candidate_id)
        request = OptimizationRequest(
            symbols=list(run.symbols), timeframe=run.timeframe, start_time=run.start_time, end_time=run.end_time,
            parameter_grid={},
        )
        candles = await self._load_once(request)
        holdout_request = BacktestRequest(symbols=list(run.symbols), timeframe=run.timeframe, start_time=run.holdout_start, end_time=run.end_time)
        result = await self._run_backtest(self._candidate_settings(selected.parameters), holdout_request, candles)
        evaluated = selected.model_copy(update={"test_metrics": self._metrics(result)})
        flags = list(evaluated.warnings)
        if (evaluated.validation_metrics.net_pnl > 0 and evaluated.test_metrics and evaluated.test_metrics.net_pnl <= 0) or (evaluated.test_metrics and evaluated.test_metrics.total_trades < self.settings.min_evaluation_trades):
            flags.append("HOLDOUT_DEGRADATION")
            evaluated = evaluated.model_copy(update={"warnings": tuple(sorted(set(flags)))})
        updated = run.model_copy(update={
            "candidates": tuple(evaluated if item.candidate_id == evaluated.candidate_id else item for item in run.candidates),
            "final_holdout_evaluated": True,
        })
        self.store.save(updated)
        return updated

    def _validate(self, request: OptimizationRequest) -> None:
        if request.timeframe != self.settings.default_timeframe:
            raise ValueError("only the configured timeframe is supported")
        if any(symbol.upper() not in self.settings.symbols for symbol in request.symbols):
            raise ValueError("unknown configured symbol")
        if (request.end_time - request.start_time).days > self.settings.max_backtest_days:
            raise ValueError("requested range exceeds max_backtest_days")
        count = 1
        for name, values in request.parameter_grid.items():
            if name.upper() not in OPTIMIZABLE_FIELDS:
                raise ValueError(f"{name} is not an optimizable Phase 8 strategy parameter")
            count *= len(values)
        if count > self.settings.max_optimization_combinations:
            raise ValueError(f"parameter grid has {count} combinations; maximum is {self.settings.max_optimization_combinations}")

    async def _load_once(self, request: OptimizationRequest) -> dict[str, list[Candle]]:
        symbols = [symbol.upper() for symbol in request.symbols]
        loaded = await asyncio.gather(*[
            self.backtest_engine.loader.load(symbol, request.timeframe, request.start_time, request.end_time)
            for symbol in symbols
        ])
        return dict(zip(symbols, loaded, strict=True))

    @staticmethod
    def _split_times(request: OptimizationRequest) -> tuple[datetime, datetime]:
        duration = request.end_time - request.start_time
        train_end = request.start_time + duration * request.train_fraction
        validation_end = train_end + duration * request.validation_fraction
        return train_end, validation_end

    @staticmethod
    def _parameter_combinations(grid: dict[str, list[int | float]]):
        names = list(grid)
        if not names:
            return iter(())
        return (dict(zip(names, values, strict=True)) for values in itertools.product(*(grid[name] for name in names)))

    def _candidate_settings(self, parameters: dict[str, int | float]) -> Settings:
        values = self.settings.model_dump()
        for name, value in parameters.items():
            values[OPTIMIZABLE_FIELDS[name.upper()]] = value
        # Constructing Settings (rather than model_copy) re-runs every cross-field validator.
        return Settings(**values)

    async def _evaluate_candidate(self, candidate_id, is_baseline, parameters, settings, request, candles, train_end, validation_end) -> OptimizationCandidate:
        train_request = BacktestRequest(symbols=request.symbols, timeframe=request.timeframe, start_time=request.start_time, end_time=train_end)
        validation_request = BacktestRequest(symbols=request.symbols, timeframe=request.timeframe, start_time=train_end, end_time=validation_end)
        train, validation = await asyncio.gather(
            self._run_backtest(settings, train_request, candles), self._run_backtest(settings, validation_request, candles)
        )
        validation_metrics = self._metrics(validation)
        flags = self._eligibility_flags(validation_metrics, len(request.symbols))
        score = self._score(validation_metrics, len(request.symbols))
        eligible = not any(flag in flags for flag in ("LOW_TRADE_COUNT", "EXCESSIVE_DRAWDOWN", "LOW_PROFIT_FACTOR"))
        return OptimizationCandidate(candidate_id=candidate_id, is_baseline=is_baseline, parameters={name.upper(): value for name, value in parameters.items()}, train_metrics=self._metrics(train), validation_metrics=validation_metrics, validation_score=score, selection_eligible=eligible, warnings=tuple(flags))

    async def _run_backtest(self, settings: Settings, request: BacktestRequest, candles: dict[str, list[Candle]]) -> BacktestResult:
        return await BacktestEngine(settings).run(request, candles)

    @staticmethod
    def _metrics(result: BacktestResult) -> EvaluationMetrics:
        return EvaluationMetrics(total_trades=result.total_trades, net_pnl=result.net_pnl, return_percent=result.return_percent, win_rate=result.win_rate, profit_factor=result.profit_factor, expectancy_per_trade=result.expectancy_per_trade, average_r_multiple=result.average_r_multiple, max_drawdown_usdt=result.max_drawdown_usdt, max_drawdown_percent=result.max_drawdown_percent, total_fees=result.total_fees, symbol_net_pnl={symbol: slice.net_pnl for symbol, slice in result.symbol_performance.items()})

    def _eligibility_flags(self, metrics: EvaluationMetrics, symbol_count: int) -> list[str]:
        flags = []
        if metrics.total_trades < self.settings.min_evaluation_trades:
            flags.append("LOW_TRADE_COUNT")
        if metrics.max_drawdown_percent > Decimal(str(self.settings.max_acceptable_drawdown_percent)):
            flags.append("EXCESSIVE_DRAWDOWN")
        if metrics.profit_factor is None or metrics.profit_factor < Decimal(str(self.settings.min_acceptable_profit_factor)):
            flags.append("LOW_PROFIT_FACTOR")
        if symbol_count > 1:
            absolute = sum((abs(value) for value in metrics.symbol_net_pnl.values()), Decimal(0))
            if absolute and max((abs(value) for value in metrics.symbol_net_pnl.values()), default=Decimal(0)) / absolute >= Decimal("0.80"):
                flags.append("SINGLE_SYMBOL_DEPENDENCE")
        return flags

    def _score(self, metrics: EvaluationMetrics, symbol_count: int) -> Decimal:
        # Explicit, bounded 0-100 validation score: expectancy 30%, PF 25%, drawdown 25%, cross-symbol consistency 20%.
        expectancy = max(Decimal(0), metrics.expectancy_per_trade or Decimal(0))
        expected_scale = Decimal(str(self.settings.backtest_starting_balance * self.settings.risk_per_trade))
        expectancy_component = min(Decimal(1), expectancy / expected_scale) if expected_scale else Decimal(0)
        profit_component = min(Decimal(1), (metrics.profit_factor or Decimal(0)) / Decimal(2))
        drawdown_cap = Decimal(str(self.settings.max_acceptable_drawdown_percent))
        drawdown_component = max(Decimal(0), Decimal(1) - metrics.max_drawdown_percent / drawdown_cap)
        positive_symbols = sum(1 for value in metrics.symbol_net_pnl.values() if value > 0)
        consistency_component = Decimal(positive_symbols) / Decimal(max(symbol_count, 1))
        score = Decimal(100) * (Decimal("0.30") * expectancy_component + Decimal("0.25") * profit_component + Decimal("0.25") * drawdown_component + Decimal("0.20") * consistency_component)
        trade_adjustment = min(Decimal(1), Decimal(metrics.total_trades) / Decimal(self.settings.min_evaluation_trades))
        return (score * trade_adjustment).quantize(Decimal("0.01"))

    def _add_stability(self, candidates: list[OptimizationCandidate]) -> list[OptimizationCandidate]:
        updated = []
        for candidate in candidates:
            neighbours = [other for other in candidates if self._one_parameter_neighbour(candidate, other)]
            if not neighbours:
                updated.append(candidate)
                continue
            differences = [abs((candidate.validation_score or Decimal(0)) - (other.validation_score or Decimal(0))) for other in neighbours]
            mean_difference = sum(differences, Decimal(0)) / len(differences)
            stability = max(Decimal(0), Decimal(100) - mean_difference).quantize(Decimal("0.01"))
            flags = list(candidate.warnings)
            if mean_difference > Decimal(20):
                flags.append("HIGH_PARAMETER_SENSITIVITY")
            updated.append(candidate.model_copy(update={"stability_score": stability, "warnings": tuple(sorted(set(flags)))}))
        return updated

    @staticmethod
    def _one_parameter_neighbour(left: OptimizationCandidate, right: OptimizationCandidate) -> bool:
        if left.candidate_id == right.candidate_id or left.parameters.keys() != right.parameters.keys():
            return False
        changed = [name for name in left.parameters if left.parameters[name] != right.parameters[name]]
        return len(changed) == 1

    async def _research_selected(self, candidate: OptimizationCandidate, settings: Settings, request: OptimizationRequest, candles: dict[str, list[Candle]]) -> OptimizationCandidate:
        _, validation_end = self._split_times(request)
        train_end, _ = self._split_times(request)
        validation = BacktestRequest(symbols=request.symbols, timeframe=request.timeframe, start_time=train_end, end_time=validation_end)
        stress_results = []
        for label, multiplier in (("normal", 1.0), ("high", 1.5), ("stress", 2.0)):
            values = settings.model_dump()
            values.update({"paper_fee_bps": settings.paper_fee_bps * multiplier, "paper_entry_slippage_bps": settings.paper_entry_slippage_bps * multiplier, "paper_exit_slippage_bps": settings.paper_exit_slippage_bps * multiplier})
            result = await self._run_backtest(Settings(**values), validation, candles)
            stress_results.append(CostStressResult(scenario=cast(Literal["normal", "high", "stress"], label), cost_multiplier=multiplier, metrics=self._metrics(result)))
        flags = list(candidate.warnings)
        normal, _, stress = stress_results
        if normal.metrics.net_pnl > 0 and stress.metrics.net_pnl < normal.metrics.net_pnl * Decimal("0.50"):
            flags.append("HIGH_COST_SENSITIVITY")
        folds = await self._walk_forward(settings, request, candles)
        if folds and sum(1 for fold in folds if fold.validation_metrics.net_pnl > 0) * 2 < len(folds):
            flags.append("WALK_FORWARD_INCONSISTENT")
        return candidate.model_copy(update={"cost_stress": tuple(stress_results), "walk_forward": tuple(folds), "warnings": tuple(sorted(set(flags)))})

    async def _walk_forward(self, settings: Settings, request: OptimizationRequest, candles: dict[str, list[Candle]]) -> list[WalkForwardFold]:
        folds = []
        train_span = timedelta(days=request.walk_forward_train_days)
        validation_span = timedelta(days=request.walk_forward_validation_days)
        step = timedelta(days=request.walk_forward_step_days)
        cursor = request.start_time
        while cursor + train_span + validation_span <= request.end_time:
            train_end = cursor + train_span
            validation_end = train_end + validation_span
            validation = BacktestRequest(symbols=request.symbols, timeframe=request.timeframe, start_time=train_end, end_time=validation_end)
            result = await self._run_backtest(settings, validation, candles)
            folds.append(WalkForwardFold(train_start=cursor, train_end=train_end, validation_start=train_end, validation_end=validation_end, validation_metrics=self._metrics(result)))
            cursor += step
        return folds
