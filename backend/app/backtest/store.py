"""Bounded in-memory storage for reproducible historical run results."""

from collections import deque

from app.backtest.models import BacktestResult


class BacktestStore:
    def __init__(self, limit: int) -> None:
        self._results: dict[str, BacktestResult] = {}
        self._order: deque[str] = deque(maxlen=limit)

    def save(self, result: BacktestResult) -> None:
        if len(self._order) == self._order.maxlen:
            oldest = self._order[0]
            self._results.pop(oldest, None)
        self._order.append(result.run_id)
        self._results[result.run_id] = result

    def get(self, run_id: str) -> BacktestResult | None:
        return self._results.get(run_id)

    def recent(self) -> list[BacktestResult]:
        return [self._results[run_id] for run_id in reversed(self._order) if run_id in self._results]
