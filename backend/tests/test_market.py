import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.exceptions import MarketDataError
from app.main import app
from app.market.exchanges.binance import BinanceMarketAdapter
from app.market.models import Candle, FeedState
from app.market.service import MarketDataService
from app.market.store import MarketStore
from app.market.validator import validate_candle


def candle(
    *,
    symbol: str = "BTCUSDT",
    open_time: datetime | None = None,
    is_closed: bool = False,
    high: str = "102",
    low: str = "99",
    open_price: str = "100",
    close: str = "101",
    volume: str = "10",
) -> Candle:
    started = open_time or datetime(2026, 1, 1, tzinfo=UTC)
    return Candle(
        symbol=symbol,
        timeframe="1m",
        open_time=started,
        close_time=started + timedelta(minutes=1) - timedelta(milliseconds=1),
        open=Decimal(open_price), high=Decimal(high), low=Decimal(low), close=Decimal(close),
        volume=Decimal(volume), is_closed=is_closed,
    )


def sample_binance_message() -> dict[str, object]:
    return {"stream": "btcusdt@kline_1m", "data": {"e": "kline", "k": {
        "t": 1767225600000, "T": 1767225659999, "s": "BTCUSDT", "i": "1m",
        "o": "100.00", "h": "102.00", "l": "99.00", "c": "101.00", "v": "12.50", "x": False,
    }}}


def test_binance_message_parsing_and_normalization() -> None:
    parsed = BinanceMarketAdapter.parse_message(sample_binance_message())
    assert parsed is not None
    assert parsed.symbol == "BTCUSDT"
    assert parsed.close == Decimal("101.00")
    assert parsed.open_time.tzinfo == UTC


def test_valid_candle_validation() -> None:
    validate_candle(candle(), {"BTCUSDT"}, "1m")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"high": "98"}, {"open_price": "-1"}, {"volume": "-1"},
        {"symbol": "DOGEUSDT"},
    ],
)
def test_invalid_candle_validation(kwargs: dict[str, str]) -> None:
    with pytest.raises(MarketDataError):
        validate_candle(candle(**kwargs), {"BTCUSDT"}, "1m")


def test_wrong_timeframe_rejected() -> None:
    invalid = candle().model_copy(update={"timeframe": "5m"})
    with pytest.raises(MarketDataError):
        validate_candle(invalid, {"BTCUSDT"}, "1m")


def test_store_open_closed_duplicate_and_out_of_order_handling() -> None:
    async def exercise() -> None:
        store = MarketStore(history_limit=2)
        first = candle()
        update = first.model_copy(update={"close": Decimal("101.5")})
        assert await store.upsert_candle(first)
        assert await store.upsert_candle(update)
        assert (await store.get_current_candle("BTCUSDT", "1m")) == update
        closed = update.model_copy(update={"is_closed": True})
        assert await store.upsert_candle(closed)
        assert not await store.upsert_candle(closed)
        older = candle(open_time=first.open_time - timedelta(minutes=1), is_closed=True)
        assert not await store.upsert_candle(older)
        assert len(await store.get_recent_candles("BTCUSDT", "1m", 10)) == 1
    asyncio.run(exercise())


def test_store_history_is_bounded() -> None:
    async def exercise() -> None:
        store = MarketStore(history_limit=2)
        start = datetime(2026, 1, 1, tzinfo=UTC)
        for minute in range(3):
            assert await store.upsert_candle(candle(open_time=start + timedelta(minutes=minute), is_closed=True))
        candles = await store.get_recent_candles("BTCUSDT", "1m", 10)
        assert [item.open_time for item in candles] == [start + timedelta(minutes=1), start + timedelta(minutes=2)]
    asyncio.run(exercise())


class FakeAdapter:
    exchange_name = "binance"
    state = FeedState.DISCONNECTED

    async def start(self) -> None:
        self.state = FeedState.CONNECTED

    async def stop(self) -> None:
        self.state = FeedState.DISCONNECTED


def test_stale_detection_and_recovery() -> None:
    async def exercise() -> None:
        settings = Settings(market_stale_after_seconds=1)
        service = MarketDataService(settings, adapter=FakeAdapter())
        service.state = FeedState.CONNECTED
        service._last_updates["BTCUSDT"] = datetime.now(UTC) - timedelta(seconds=2)
        assert service.status_snapshot().status == FeedState.STALE
        service.state = FeedState.STALE
        await service.ingest_candle(candle())
        assert service.state == FeedState.CONNECTED
    asyncio.run(exercise())


def test_reconnect_backoff_is_bounded() -> None:
    assert BinanceMarketAdapter.reconnect_delay(1, 8, jitter=0) == 1
    assert BinanceMarketAdapter.reconnect_delay(4, 8, jitter=0) == 8
    assert BinanceMarketAdapter.reconnect_delay(8, 8, jitter=0) == 8


def test_websocket_candle_event_serialization() -> None:
    event = {"type": "market.candle", "data": candle().model_dump(mode="json")}
    assert event["data"]["close"] == "101"
    assert event["data"]["is_closed"] is False


def test_market_rest_endpoints_and_websocket_snapshot() -> None:
    with TestClient(app) as client:
        status_response = client.get("/api/market/status")
        candles_response = client.get("/api/market/BTCUSDT/candles?limit=100")
        assert status_response.status_code == 200
        assert status_response.json()["exchange"] == "binance"
        assert candles_response.status_code == 200
        assert candles_response.json() == []
        assert client.get("/api/market/DOGEUSDT/candles").status_code == 404
        assert client.get("/api/market/BTCUSDT/candles?limit=501").status_code == 422
        with client.websocket_connect("/ws/market") as websocket:
            event = websocket.receive_json()
        assert event["type"] == "market.snapshot"
        assert event["data"]["status"]["exchange"] == "binance"
