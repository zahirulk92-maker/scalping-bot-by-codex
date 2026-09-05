import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.config import Settings
from app.indicators.calculations.atr import true_range
from app.indicators.calculations.ema import next_ema, simple_average
from app.indicators.calculations.rsi import rsi_from_averages
from app.indicators.calculations.volume import volume_average
from app.indicators.calculations.vwap import typical_price
from app.indicators.engine import IndicatorEngine
from app.main import app
from app.market.models import Candle
from app.market.service import MarketDataService


def closed_candle(symbol: str, minute: int, close: str, volume: str = "10") -> Candle:
    opened = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minute)
    price = Decimal(close)
    return Candle(symbol=symbol, timeframe="1m", open_time=opened, close_time=opened + timedelta(minutes=1) - timedelta(milliseconds=1), open=price, high=price + 1, low=price - 1, close=price, volume=Decimal(volume), is_closed=True)


def small_settings() -> Settings:
    return Settings(ema_fast_period=2, ema_slow_period=3, rsi_period=2, atr_period=2, volume_ma_period=2)


def test_indicator_calculation_primitives() -> None:
    assert simple_average([Decimal(1), Decimal(2), Decimal(3)]) == Decimal(2)
    assert next_ema(Decimal(4), Decimal(2), 3) == Decimal(3)
    assert rsi_from_averages(Decimal(0), Decimal(0)) == Decimal(50)
    assert rsi_from_averages(Decimal(1), Decimal(0)) == Decimal(100)
    assert true_range(Decimal(12), Decimal(10), Decimal(9)) == Decimal(3)
    assert typical_price(Decimal(12), Decimal(9), Decimal(12)) == Decimal(11)
    assert volume_average([Decimal(10), Decimal(20)]) == Decimal(15)


def test_engine_closed_candles_readiness_and_idempotency() -> None:
    async def exercise() -> None:
        engine = IndicatorEngine(small_settings())
        assert await engine.process_candle(closed_candle("BTCUSDT", 0, "100")) is not None
        assert not (await engine.latest("BTCUSDT")).is_ready
        assert await engine.process_candle(closed_candle("BTCUSDT", 1, "101")) is not None
        snapshot = await engine.process_candle(closed_candle("BTCUSDT", 2, "102", "20"))
        assert snapshot is not None and snapshot.is_ready
        assert snapshot.ema_9 == Decimal("101.5")
        assert snapshot.ema_21 == Decimal("101")
        assert snapshot.rsi_14 == Decimal(100)
        assert snapshot.atr_14 is not None and snapshot.atr_14 >= 0
        assert snapshot.vwap is not None and snapshot.vwap > 0
        assert snapshot.volume_ma_20 == Decimal(15)
        assert await engine.process_candle(closed_candle("BTCUSDT", 2, "102", "20")) is None
        assert await engine.process_candle(closed_candle("BTCUSDT", 1, "101")) is None
        assert await engine.process_candle(closed_candle("BTCUSDT", 3, "103").model_copy(update={"is_closed": False})) is None
    asyncio.run(exercise())


def test_engine_multi_symbol_isolation_and_vwap_daily_reset() -> None:
    async def exercise() -> None:
        engine = IndicatorEngine(small_settings())
        for minute, price in enumerate(("100", "101", "102")):
            await engine.process_candle(closed_candle("BTCUSDT", minute, price))
            await engine.process_candle(closed_candle("ETHUSDT", minute, str(Decimal(price) * 2)))
        assert (await engine.latest("BTCUSDT")).ema_21 == Decimal(101)
        assert (await engine.latest("ETHUSDT")).ema_21 == Decimal(202)
        next_day = closed_candle("BTCUSDT", 24 * 60, "200", "5")
        snapshot = await engine.process_candle(next_day)
        assert snapshot is not None and snapshot.vwap == Decimal(200)
    asyncio.run(exercise())


def test_historical_warmup_and_failure_are_safe() -> None:
    async def exercise() -> None:
        engine = IndicatorEngine(small_settings())
        async def successful(_: str, __: str, ___: int) -> list[Candle]:
            return [closed_candle("BTCUSDT", index, str(100 + index)) for index in range(4)]
        await engine.warm_up(successful)
        assert (await engine.latest("BTCUSDT")).is_ready
        failed = IndicatorEngine(small_settings())
        async def failure(_: str, __: str, ___: int) -> list[Candle]:
            raise RuntimeError("offline")
        await failed.warm_up(failure)
        assert not (await failed.latest("BTCUSDT")).is_ready
    asyncio.run(exercise())


def test_indicator_rest_endpoints() -> None:
    with TestClient(app) as client:
        response = client.get("/api/indicators/BTCUSDT")
        assert response.status_code == 200
        assert response.json()["is_ready"] is False
        assert client.get("/api/indicators/status").status_code == 200
        assert client.get("/api/indicators/BTCUSDT/history?limit=10").json() == []
        assert client.get("/api/indicators/DOGEUSDT").status_code == 404


class CaptureClient:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def send_json(self, event: dict[str, object]) -> None:
        self.events.append(event)


class Adapter:
    exchange_name = "binance"

    async def start(self) -> None: pass
    async def stop(self) -> None: pass
    async def fetch_historical_candles(self, *_: object) -> list[Candle]: return []


def test_closed_candle_broadcasts_indicator_snapshot() -> None:
    async def exercise() -> None:
        settings = small_settings()
        engine = IndicatorEngine(settings)
        service = MarketDataService(settings, adapter=Adapter(), on_closed_candle=engine.process_candle)
        engine.set_snapshot_handler(lambda snapshot: service.broadcast({"type": "indicator.snapshot", "data": snapshot.model_dump(mode="json")}))
        for minute, price in enumerate(("100", "101", "102")):
            await engine.process_candle(closed_candle("BTCUSDT", minute, price), notify=False)
        client = CaptureClient()
        service._clients.add(client)  # Test-only in-memory dashboard client.
        await service.ingest_candle(closed_candle("BTCUSDT", 3, "103"))
        assert any(event["type"] == "indicator.snapshot" for event in client.events)
    asyncio.run(exercise())
