"""Bounded in-memory optimization results; research data resets on restart."""

from collections import deque

from app.optimization.models import OptimizationRun


class OptimizationStore:
    def __init__(self, limit: int) -> None:
        self._runs: dict[str, OptimizationRun] = {}
        self._order: deque[str] = deque(maxlen=limit)

    def save(self, run: OptimizationRun) -> None:
        if run.run_id not in self._runs and len(self._order) == self._order.maxlen:
            self._runs.pop(self._order[0], None)
        if run.run_id not in self._runs:
            self._order.append(run.run_id)
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> OptimizationRun | None:
        return self._runs.get(run_id)

    def recent(self) -> list[OptimizationRun]:
        return [self._runs[run_id] for run_id in reversed(self._order) if run_id in self._runs]
