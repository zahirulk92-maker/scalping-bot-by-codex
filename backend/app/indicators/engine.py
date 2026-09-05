"""Closed-candle-only, idempotent technical indicator engine."""

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from app.config import Settings
from app.indicators.calculations.atr import true_range
from app.indicators.calculations.ema import next_ema, simple_average
from app.indicators.calculations.rsi import rsi_from_averages
from app.indicators.calculations.volume import volume_average
from app.indicators.calculations.vwap import typical_price
from app.indicators.models import IndicatorSnapshot
from app.market.models import Candle
from app.market.validator import validate_candle

logger = logging.getLogger(__name__)
SnapshotHandler = Callable[[IndicatorSnapshot], Awaitable[None]]


@dataclass
class SymbolIndicatorState:
    fast_seed: list[Decimal] = field(default_factory=list)
    slow_seed: list[Decimal] = field(default_factory=list)
    ema_fast: Decimal | None = None
    ema_slow: Decimal | None = None
    previous_close: Decimal | None = None
    rsi_gains: list[Decimal] = field(default_factory=list)
    rsi_losses: list[Decimal] = field(default_factory=list)
    average_gain: Decimal | None = None
    average_loss: Decimal | None = None
    atr_seed: list[Decimal] = field(default_factory=list)
    atr: Decimal | None = None
    session_day: date | None = None
    vwap_numerator: Decimal = Decimal(0)
    vwap_volume: Decimal = Decimal(0)
    volumes: deque[Decimal] = field(default_factory=deque)
    last_open_time: datetime | None = None


class IndicatorEngine:
    """Maintains isolated, bounded incremental state for each symbol/timeframe."""

    def __init__(self, settings: Settings, on_snapshot: SnapshotHandler | None = None) -> None:
        self.settings = settings
        self._on_snapshot = on_snapshot
        self._states: dict[tuple[str, str], SymbolIndicatorState] = {}
        self._latest: dict[tuple[str, str], IndicatorSnapshot] = {}
        self._history: dict[tuple[str, str], deque[IndicatorSnapshot]] = {}
        self._lock = asyncio.Lock()
        logger.info("Indicator engine initialized; official values use closed candles only")

    def set_snapshot_handler(self, handler: SnapshotHandler) -> None:
        self._on_snapshot = handler

    async def warm_up(self, fetcher: Callable[[str, str, int], Awaitable[list[Candle]]]) -> None:
        """Best-effort public historical warm-up; failures never stop market ingestion."""
        required = max(self.settings.ema_slow_period, self.settings.rsi_period + 1, self.settings.atr_period, self.settings.volume_ma_period)
        logger.info("Indicator warm-up started")
        for symbol in self.settings.symbols:
            try:
                candles = await fetcher(symbol, self.settings.default_timeframe, required + 5)
                for candle in sorted(candles, key=lambda item: item.open_time):
                    await self.process_candle(candle, notify=False)
                logger.info("Indicator warm-up completed for %s", symbol)
            except Exception as error:
                logger.warning("Indicator warm-up failed for %s: %s", symbol, error)

    async def process_candle(self, candle: Candle, notify: bool = True) -> IndicatorSnapshot | None:
        """Process one validated closed candle exactly once; open candles never advance state."""
        if not candle.is_closed:
            return None
        validate_candle(candle, set(self.settings.symbols), self.settings.default_timeframe)
        key = (candle.symbol, candle.timeframe)
        async with self._lock:
            state = self._states.setdefault(key, SymbolIndicatorState(volumes=deque(maxlen=self.settings.volume_ma_period)))
            if state.last_open_time is not None and candle.open_time <= state.last_open_time:
                logger.debug("Ignored duplicate/out-of-order indicator candle for %s", candle.symbol)
                return None
            snapshot = self._advance(state, candle)
            state.last_open_time = candle.open_time
            self._latest[key] = snapshot
            history = self._history.setdefault(key, deque(maxlen=self.settings.market_history_limit))
            history.append(snapshot)
        if notify and self._on_snapshot:
            await self._on_snapshot(snapshot)
        return snapshot

    def _advance(self, state: SymbolIndicatorState, candle: Candle) -> IndicatorSnapshot:
        fast = self._update_ema(candle.close, state.fast_seed, state.ema_fast, self.settings.ema_fast_period)
        if fast is not None:
            state.ema_fast = fast
        slow = self._update_ema(candle.close, state.slow_seed, state.ema_slow, self.settings.ema_slow_period)
        if slow is not None:
            state.ema_slow = slow

        rsi = self._update_rsi(state, candle.close)
        atr = self._update_atr(state, candle)
        vwap = self._update_vwap(state, candle)
        state.volumes.append(candle.volume)
        volume_ma = volume_average(list(state.volumes)) if len(state.volumes) == self.settings.volume_ma_period else None
        state.previous_close = candle.close

        ready = all(value is not None for value in (state.ema_fast, state.ema_slow, rsi, atr, vwap, volume_ma))
        return IndicatorSnapshot(
            symbol=candle.symbol, timeframe=candle.timeframe, candle_open_time=candle.open_time, candle_close_time=candle.close_time,
            close=candle.close,
            ema_9=state.ema_fast if ready else None, ema_21=state.ema_slow if ready else None,
            rsi_14=rsi if ready else None, atr_14=atr if ready else None, vwap=vwap if ready else None,
            volume=candle.volume, volume_ma_20=volume_ma if ready else None, is_ready=ready, calculated_at=datetime.now(UTC),
        )

    @staticmethod
    def _update_ema(value: Decimal, seed: list[Decimal], previous: Decimal | None, period: int) -> Decimal | None:
        if previous is not None:
            return next_ema(value, previous, period)
        seed.append(value)
        return simple_average(seed) if len(seed) == period else None

    def _update_rsi(self, state: SymbolIndicatorState, close: Decimal) -> Decimal | None:
        if state.previous_close is None:
            return None
        change = close - state.previous_close
        gain, loss = max(change, Decimal(0)), max(-change, Decimal(0))
        if state.average_gain is None or state.average_loss is None:
            state.rsi_gains.append(gain)
            state.rsi_losses.append(loss)
            if len(state.rsi_gains) < self.settings.rsi_period:
                return None
            state.average_gain = simple_average(state.rsi_gains)
            state.average_loss = simple_average(state.rsi_losses)
        else:
            period = Decimal(self.settings.rsi_period)
            state.average_gain = (state.average_gain * (period - 1) + gain) / period
            state.average_loss = (state.average_loss * (period - 1) + loss) / period
        return rsi_from_averages(state.average_gain, state.average_loss)

    def _update_atr(self, state: SymbolIndicatorState, candle: Candle) -> Decimal | None:
        current_tr = true_range(candle.high, candle.low, state.previous_close)
        if state.atr is None:
            state.atr_seed.append(current_tr)
            if len(state.atr_seed) < self.settings.atr_period:
                return None
            state.atr = simple_average(state.atr_seed)
        else:
            period = Decimal(self.settings.atr_period)
            state.atr = (state.atr * (period - 1) + current_tr) / period
        return state.atr

    @staticmethod
    def _update_vwap(state: SymbolIndicatorState, candle: Candle) -> Decimal | None:
        candle_day = candle.open_time.date()
        if state.session_day != candle_day:
            state.session_day = candle_day
            state.vwap_numerator, state.vwap_volume = Decimal(0), Decimal(0)
        state.vwap_numerator += typical_price(candle.high, candle.low, candle.close) * candle.volume
        state.vwap_volume += candle.volume
        return state.vwap_numerator / state.vwap_volume if state.vwap_volume > 0 else None

    async def latest(self, symbol: str) -> IndicatorSnapshot:
        key = (symbol, self.settings.default_timeframe)
        async with self._lock:
            return self._latest.get(key, IndicatorSnapshot(symbol=symbol, timeframe=self.settings.default_timeframe))

    async def history(self, symbol: str, limit: int) -> list[IndicatorSnapshot]:
        key = (symbol, self.settings.default_timeframe)
        async with self._lock:
            return list(self._history.get(key, ()))[-limit:]

    async def readiness(self) -> dict[str, dict[str, bool]]:
        return {symbol: {"ready": (await self.latest(symbol)).is_ready} for symbol in self.settings.symbols}
