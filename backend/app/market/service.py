"""Market-data coordinator used by REST, dashboard WebSockets, and later phases."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

from app.config import Settings
from app.core.exceptions import MarketDataError
from app.market.exchanges.base import MarketDataAdapter
from app.market.exchanges.binance import BinanceMarketAdapter
from app.market.models import Candle, FeedState, MarketFeedStatus, SymbolFeedStatus
from app.market.store import MarketStore
from app.market.validator import validate_candle

logger = logging.getLogger(__name__)
ClosedCandleHandler = Callable[[Candle], Awaitable[object]]
MarketCandleHandler = Callable[[Candle], Awaitable[object]]
EventObserver = Callable[[str, dict[str, Any]], Awaitable[None]]


class MarketDataService:
    def __init__(self, settings: Settings, adapter: MarketDataAdapter | None = None, on_closed_candle: ClosedCandleHandler | None = None, on_market_candle: MarketCandleHandler | None = None) -> None:
        self.settings = settings
        self.store = MarketStore(settings.market_history_limit)
        self.state = FeedState.DISCONNECTED
        self._last_updates: dict[str, datetime] = {}
        self._clients: set[WebSocket] = set()
        self._client_lock = asyncio.Lock()
        self._accepting = True
        self._freshness_task: asyncio.Task[None] | None = None
        self._on_closed_candle = on_closed_candle
        self._on_market_candle = on_market_candle
        self._event_observer: EventObserver | None = None
        self.messages_received = 0
        self.valid_candles = 0
        self.invalid_candles = 0
        self.reconnect_count = 0
        self.adapter = adapter or BinanceMarketAdapter(
            settings.symbols,
            settings.default_timeframe,
            self.ingest_candle,
            self.update_feed_state,
            settings.market_reconnect_max_seconds,
        )

    async def start(self) -> None:
        self._accepting = True
        self._freshness_task = asyncio.create_task(self._monitor_freshness(), name="market-freshness")
        if self.settings.market_data_enabled:
            await self.adapter.start()
        else:
            logger.info("Market feed disabled by configuration")

    async def stop(self) -> None:
        logger.info("Shutting down market-data service")
        self._accepting = False
        if self._freshness_task:
            self._freshness_task.cancel()
            try:
                await self._freshness_task
            except asyncio.CancelledError:
                pass
            self._freshness_task = None
        await self.adapter.stop()
        async with self._client_lock:
            clients = list(self._clients)
            self._clients.clear()
        for client in clients:
            try:
                await client.close(code=1001)
            except RuntimeError:
                pass

    async def update_feed_state(self, state: FeedState) -> None:
        if state == FeedState.RECONNECTING:
            self.reconnect_count += 1
        self.state = state
        await self.broadcast_status()

    def set_market_candle_handler(self, handler: MarketCandleHandler) -> None:
        """Attach later-phase consumers without coupling them to the market adapter."""
        self._on_market_candle = handler

    def set_event_observer(self, observer: EventObserver) -> None:
        self._event_observer = observer

    async def ingest_candle(self, candle: Candle) -> None:
        """Validate, store and broadcast one public market candle safely."""
        self.messages_received += 1
        if not self._accepting:
            return
        try:
            validate_candle(candle, set(self.settings.symbols), self.settings.default_timeframe)
        except MarketDataError as error:
            self.invalid_candles += 1
            logger.warning("Rejected invalid market candle: %s", error)
            return
        self.valid_candles += 1
        if not await self.store.upsert_candle(candle):
            return
        self._last_updates[candle.symbol] = datetime.now(UTC)
        if self.state == FeedState.STALE:
            logger.info("Market feed recovered from stale state")
            self.state = FeedState.CONNECTED
        # Existing positions and older pending plans see this price before a new
        # closed-candle strategy/risk plan can be created from it.
        if self._on_market_candle:
            await self._on_market_candle(candle)
        if candle.is_closed and self._on_closed_candle:
            await self._on_closed_candle(candle)
        payload = candle.model_dump(mode="json")
        if self._event_observer:
            await self._event_observer("market.candle", payload)
        await self.broadcast({"type": "market.candle", "data": payload})

    def status_snapshot(self) -> MarketFeedStatus:
        now = datetime.now(UTC)
        symbols: dict[str, SymbolFeedStatus] = {}
        stale_after = self.settings.market_stale_after_seconds
        for symbol in self.settings.symbols:
            last_update = self._last_updates.get(symbol)
            is_stale = last_update is not None and (now - last_update).total_seconds() > stale_after
            symbol_state = FeedState.STALE if is_stale else self.state
            symbols[symbol] = SymbolFeedStatus(status=symbol_state, last_update=last_update)
        overall = FeedState.STALE if any(item.status == FeedState.STALE for item in symbols.values()) else self.state
        return MarketFeedStatus(exchange=self.adapter.exchange_name, status=overall, timeframe=self.settings.default_timeframe, symbols=symbols)

    async def snapshot_event(self) -> dict[str, Any]:
        current = []
        for symbol in self.settings.symbols:
            candle = await self.store.get_current_candle(symbol, self.settings.default_timeframe)
            if candle:
                current.append(candle.model_dump(mode="json"))
        return {"type": "market.snapshot", "data": {"status": self.status_snapshot().model_dump(mode="json"), "current_candles": current}}

    async def connect_dashboard(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._client_lock:
            self._clients.add(websocket)
        await websocket.send_json(await self.snapshot_event())

    async def disconnect_dashboard(self, websocket: WebSocket) -> None:
        async with self._client_lock:
            self._clients.discard(websocket)

    async def broadcast(self, event: dict[str, Any]) -> None:
        async with self._client_lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        for client in clients:
            try:
                await asyncio.wait_for(client.send_json(event), timeout=1)
            except (RuntimeError, OSError):
                dead.append(client)
        if dead:
            async with self._client_lock:
                self._clients.difference_update(dead)

    async def broadcast_status(self) -> None:
        payload = self.status_snapshot().model_dump(mode="json")
        if self._event_observer:
            await self._event_observer("market.status", payload)
        await self.broadcast({"type": "market.status", "data": payload})

    async def _monitor_freshness(self) -> None:
        try:
            while True:
                await asyncio.sleep(1)
                next_state = self.status_snapshot().status
                if next_state == FeedState.STALE and self.state != FeedState.STALE:
                    logger.warning("Market feed is stale")
                    self.state = FeedState.STALE
                    await self.broadcast_status()
        except asyncio.CancelledError:
            raise
