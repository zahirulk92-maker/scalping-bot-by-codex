"""Bounded in-memory plan store and explicit simulated account state."""

import asyncio
from collections import deque
from decimal import Decimal

from app.config import Settings
from app.risk.models import RiskAccountState, TradePlan


class RiskStore:
    def __init__(self, settings: Settings, account_state: RiskAccountState | None = None) -> None:
        self._account = account_state or RiskAccountState(current_equity=Decimal(str(settings.starting_balance)))
        self._latest: dict[tuple[str, str], TradePlan] = {}
        self._history: dict[tuple[str, str], deque[TradePlan]] = {}
        self._lock = asyncio.Lock()
        self._limit = settings.market_history_limit

    async def account_state(self) -> RiskAccountState:
        async with self._lock:
            return self._account

    async def replace_account_state(self, account_state: RiskAccountState) -> None:
        async with self._lock:
            self._account = account_state

    async def save(self, plan: TradePlan) -> None:
        key = (plan.symbol, plan.timeframe)
        async with self._lock:
            self._latest[key] = plan
            self._history.setdefault(key, deque(maxlen=self._limit)).append(plan)

    async def latest(self, symbol: str, timeframe: str) -> TradePlan | None:
        async with self._lock:
            return self._latest.get((symbol, timeframe))

    async def history(self, symbol: str, timeframe: str, limit: int) -> list[TradePlan]:
        async with self._lock:
            return list(self._history.get((symbol, timeframe), ()))[-limit:]
