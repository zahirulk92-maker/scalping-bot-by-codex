"""Public Binance historical kline loader with complete-range CSV cache checks."""

import csv
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx

from app.market.models import Candle
from app.market.validator import validate_candle


class HistoricalDataLoader:
    def __init__(self, cache_root: Path, configured_symbols: set[str]) -> None:
        self.cache_root = cache_root
        self.configured_symbols = configured_symbols

    async def load(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        path = self.cache_root / f"{symbol}_{timeframe}_{int(start.timestamp())}_{int(end.timestamp())}.csv"
        if path.exists():
            candles = self._read(path)
            if candles and candles[0].open_time >= start and candles[-1].close_time <= end:
                return candles
        candles = await self._fetch(symbol, timeframe, start, end)
        if candles:
            self._write(path, candles)
        return candles

    async def _fetch(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        cursor = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        candles: list[Candle] = []
        async with httpx.AsyncClient(timeout=20) as client:
            while cursor < end_ms:
                response = await client.get("https://api.binance.com/api/v3/klines", params={"symbol": symbol, "interval": timeframe, "startTime": cursor, "endTime": end_ms, "limit": 1000})
                response.raise_for_status()
                rows = response.json()
                if not rows:
                    break
                for row in rows:
                    candle = Candle(symbol=symbol, timeframe=timeframe, open_time=datetime.fromtimestamp(int(row[0]) / 1000, UTC), close_time=datetime.fromtimestamp(int(row[6]) / 1000, UTC), open=Decimal(str(row[1])), high=Decimal(str(row[2])), low=Decimal(str(row[3])), close=Decimal(str(row[4])), volume=Decimal(str(row[5])), is_closed=True)
                    validate_candle(candle, self.configured_symbols, timeframe)
                    if start <= candle.open_time and candle.close_time <= end:
                        candles.append(candle)
                next_cursor = int(rows[-1][0]) + 60_000
                if next_cursor <= cursor:
                    break
                cursor = next_cursor
        return candles

    def _read(self, path: Path) -> list[Candle]:
        with path.open(newline="", encoding="utf-8") as file:
            rows = list(csv.DictReader(file))
        return [Candle(symbol=row["symbol"], timeframe=row["timeframe"], open_time=datetime.fromisoformat(row["open_time"]), close_time=datetime.fromisoformat(row["close_time"]), open=Decimal(row["open"]), high=Decimal(row["high"]), low=Decimal(row["low"]), close=Decimal(row["close"]), volume=Decimal(row["volume"]), is_closed=True) for row in rows]

    def _write(self, path: Path, candles: list[Candle]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["symbol", "timeframe", "open_time", "close_time", "open", "high", "low", "close", "volume"])
            writer.writeheader()
            for candle in candles:
                writer.writerow({"symbol": candle.symbol, "timeframe": candle.timeframe, "open_time": candle.open_time.isoformat(), "close_time": candle.close_time.isoformat(), "open": candle.open, "high": candle.high, "low": candle.low, "close": candle.close, "volume": candle.volume})
