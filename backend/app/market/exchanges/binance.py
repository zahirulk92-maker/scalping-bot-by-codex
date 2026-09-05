"""Public Binance Spot combined-kline adapter. It has no account capabilities."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from random import uniform

import httpx
from websockets.asyncio.client import connect

from app.market.exchanges.base import CandleHandler, StateHandler
from app.market.models import Candle, FeedState

logger = logging.getLogger(__name__)


class BinanceMarketAdapter:
    exchange_name = "binance"

    def __init__(
        self,
        symbols: list[str],
        timeframe: str,
        on_candle: CandleHandler,
        on_state_change: StateHandler,
        reconnect_max_seconds: int,
    ) -> None:
        self._symbols = symbols
        self._timeframe = timeframe
        self._on_candle = on_candle
        self._on_state_change = on_state_change
        self._reconnect_max_seconds = reconnect_max_seconds
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self.state = FeedState.DISCONNECTED

    @property
    def stream_url(self) -> str:
        streams = "/".join(f"{symbol.lower()}@kline_{self._timeframe}" for symbol in self._symbols)
        return f"wss://stream.binance.com:9443/stream?streams={streams}"

    @staticmethod
    def parse_message(payload: str | bytes | dict[str, object]) -> Candle | None:
        """Translate one combined-stream message into the internal model."""
        if isinstance(payload, (str, bytes)):
            decoded = json.loads(payload)
            if not isinstance(decoded, dict):
                return None
            payload = decoded
        data = payload.get("data", payload)
        if not isinstance(data, dict) or data.get("e") != "kline":
            return None
        kline = data.get("k")
        if not isinstance(kline, dict):
            return None
        return Candle(
            symbol=str(kline["s"]).upper(),
            timeframe=str(kline["i"]),
            open_time=datetime.fromtimestamp(int(kline["t"]) / 1000, tz=UTC),
            close_time=datetime.fromtimestamp(int(kline["T"]) / 1000, tz=UTC),
            open=Decimal(str(kline["o"])),
            high=Decimal(str(kline["h"])),
            low=Decimal(str(kline["l"])),
            close=Decimal(str(kline["c"])),
            volume=Decimal(str(kline["v"])),
            is_closed=bool(kline["x"]),
        )

    @staticmethod
    def reconnect_delay(attempt: int, maximum: int, jitter: float = 0.2) -> float:
        base = min(float(maximum), float(2 ** max(0, attempt - 1)))
        return base if jitter == 0 else min(float(maximum), base + uniform(0, base * jitter))

    async def fetch_historical_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        """Retrieve public Spot klines and normalize them into shared candle models."""
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://api.binance.com/api/v3/klines", params={"symbol": symbol.upper(), "interval": timeframe, "limit": limit})
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            raise ValueError("Binance historical kline response was not a list")
        now = datetime.now(UTC)
        candles: list[Candle] = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 7:
                raise ValueError("Binance historical kline row was malformed")
            close_time = datetime.fromtimestamp(int(row[6]) / 1000, tz=UTC)
            if close_time >= now:
                continue
            candles.append(Candle(symbol=symbol.upper(), timeframe=timeframe, open_time=datetime.fromtimestamp(int(row[0]) / 1000, tz=UTC), close_time=close_time, open=Decimal(str(row[1])), high=Decimal(str(row[2])), low=Decimal(str(row[3])), close=Decimal(str(row[4])), volume=Decimal(str(row[5])), is_closed=True))
        return candles

    async def _set_state(self, state: FeedState) -> None:
        self.state = state
        await self._on_state_change(state)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name="binance-market-feed")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._set_state(FeedState.DISCONNECTED)

    async def _run(self) -> None:
        attempt = 0
        while self._running:
            await self._set_state(FeedState.CONNECTING if attempt == 0 else FeedState.RECONNECTING)
            try:
                logger.info("Connecting to Binance public market feed")
                async with connect(self.stream_url, ping_interval=20, ping_timeout=20) as websocket:
                    attempt = 0
                    await self._set_state(FeedState.CONNECTED)
                    logger.info("Binance public market feed connected")
                    async for message in websocket:
                        try:
                            candle = self.parse_message(message)
                            if candle:
                                await self._on_candle(candle)
                        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                            logger.warning("Rejected malformed Binance market message: %s", error)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("Binance feed disconnected: %s", error)
                await self._set_state(FeedState.ERROR)
            if not self._running:
                break
            attempt += 1
            delay = self.reconnect_delay(attempt, self._reconnect_max_seconds)
            logger.info("Reconnecting to Binance public market feed in %.1fs", delay)
            await asyncio.sleep(delay)
