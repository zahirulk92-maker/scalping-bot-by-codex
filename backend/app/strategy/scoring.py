"""Explicit, intentionally simple rule weights for Phase 4 signals."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreWeights:
    trend: int = 30
    vwap: int = 20
    rsi: int = 20
    volume: int = 20
    atr: int = 10

    @property
    def total(self) -> int:
        return self.trend + self.vwap + self.rsi + self.volume + self.atr


WEIGHTS = ScoreWeights()
