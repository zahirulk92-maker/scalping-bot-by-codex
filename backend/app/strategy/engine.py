"""Idempotent signal-only engine driven exclusively by indicator snapshots."""

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.config import Settings
from app.indicators.models import IndicatorSnapshot
from app.market.models import FeedState, MarketFeedStatus
from app.strategy.models import SignalContext, SignalDirection, SignalSnapshot
from app.strategy.rules import evaluate

logger = logging.getLogger(__name__)
SignalHandler = Callable[[SignalSnapshot], Awaitable[None]]
MarketStatusProvider = Callable[[], MarketFeedStatus]


class StrategyEngine:
    """Stores bounded per-symbol signal history and never performs execution."""

    def __init__(self, settings: Settings, market_status_provider: MarketStatusProvider | None = None, on_signal: SignalHandler | None = None) -> None:
        self.settings = settings
        self._market_status_provider = market_status_provider
        self._on_signal = on_signal
        self._latest: dict[tuple[str, str], SignalSnapshot] = {}
        self._history: dict[tuple[str, str], deque[SignalSnapshot]] = {}
        self._last_open_time: dict[tuple[str, str], datetime] = {}
        self._lock = asyncio.Lock()
        logger.info("Strategy engine initialized in signal-only mode; execution is disabled")

    async def process_snapshot(self, snapshot: IndicatorSnapshot) -> SignalSnapshot | None:
        """Emit at most one official signal for each symbol/timeframe/closed candle."""
        key = (snapshot.symbol, snapshot.timeframe)
        if snapshot.candle_open_time is None:
            return None
        async with self._lock:
            last_open_time = self._last_open_time.get(key)
            if last_open_time is not None and snapshot.candle_open_time <= last_open_time:
                logger.debug("Ignored duplicate/out-of-order strategy snapshot for %s", snapshot.symbol)
                return None
            signal = self._build_signal(snapshot)
            self._last_open_time[key] = snapshot.candle_open_time
            self._latest[key] = signal
            self._history.setdefault(key, deque(maxlen=self.settings.market_history_limit)).append(signal)
        if self._on_signal:
            await self._on_signal(signal)
        return signal

    def _build_signal(self, snapshot: IndicatorSnapshot) -> SignalSnapshot:
        context = SignalContext(
            close=snapshot.close, ema_9=snapshot.ema_9, ema_21=snapshot.ema_21, rsi_14=snapshot.rsi_14,
            atr_14=snapshot.atr_14, vwap=snapshot.vwap, volume=snapshot.volume, volume_ma_20=snapshot.volume_ma_20,
        )
        feed_reason = self._unhealthy_feed_reason(snapshot.symbol)
        if feed_reason:
            return SignalSnapshot(
                signal_id=self._signal_id(snapshot), symbol=snapshot.symbol, timeframe=snapshot.timeframe, reasons=(feed_reason,),
                candle_open_time=snapshot.candle_open_time, candle_close_time=snapshot.candle_close_time,
                generated_at=datetime.now(UTC), context=context,
            )
        result = evaluate(snapshot, self.settings)
        actionable = result.mandatory_rules_passed and result.score >= self.settings.signal_min_score
        return SignalSnapshot(
            signal_id=self._signal_id(snapshot), symbol=snapshot.symbol, timeframe=snapshot.timeframe,
            direction=result.direction if actionable else SignalDirection.NO_TRADE,
            score=result.score, confidence=result.score / 100, reasons=result.reasons,
            candle_open_time=snapshot.candle_open_time, candle_close_time=snapshot.candle_close_time,
            generated_at=datetime.now(UTC), is_actionable=actionable, context=context,
        )

    @staticmethod
    def _signal_id(snapshot: IndicatorSnapshot) -> str:
        return f"signal:{snapshot.symbol}:{snapshot.timeframe}:{snapshot.candle_open_time.isoformat()}" if snapshot.candle_open_time else ""

    def _unhealthy_feed_reason(self, symbol: str) -> str | None:
        if self._market_status_provider is None:
            return None
        status = self._market_status_provider()
        symbol_status = status.symbols.get(symbol)
        if (symbol_status and symbol_status.status == FeedState.STALE) or (symbol_status is None and status.status == FeedState.STALE):
            return "Market data is stale"
        return None

    async def latest(self, symbol: str) -> SignalSnapshot:
        key = (symbol, self.settings.default_timeframe)
        async with self._lock:
            return self._latest.get(key, SignalSnapshot(symbol=symbol, timeframe=self.settings.default_timeframe, reasons=("No closed-candle signal available",)))

    async def history(self, symbol: str, limit: int) -> list[SignalSnapshot]:
        key = (symbol, self.settings.default_timeframe)
        async with self._lock:
            return list(self._history.get(key, ()))[-limit:]

    async def readiness(self) -> dict[str, dict[str, object]]:
        return {symbol: {"has_signal": (await self.latest(symbol)).candle_open_time is not None} for symbol in self.settings.symbols}
