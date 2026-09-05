"""Bounded in-memory paper lifecycle state; it intentionally does not persist."""

from collections import deque

from app.config import Settings
from app.execution.models import ClosedPaperTrade, PaperAccount, PaperPosition
from app.risk.models import TradePlan


class PaperExecutionStore:
    def __init__(self, settings: Settings, account: PaperAccount) -> None:
        self.account = account
        self.pending: dict[str, TradePlan] = {}
        self.open_positions: dict[str, PaperPosition] = {}
        self.closed_trades: deque[ClosedPaperTrade] = deque(maxlen=settings.max_paper_trade_history)
        self.latest_trade_by_symbol: dict[str, ClosedPaperTrade] = {}
        self.seen_plan_ids: deque[str] = deque(maxlen=settings.max_paper_trade_history * 2)
