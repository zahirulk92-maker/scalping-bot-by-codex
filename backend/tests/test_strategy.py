import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.indicators.models import IndicatorSnapshot
from app.main import app
from app.market.models import FeedState, MarketFeedStatus, SymbolFeedStatus
from app.strategy.engine import StrategyEngine
from app.strategy.models import SignalDirection


def ready_snapshot(minute: int = 0, **updates: object) -> IndicatorSnapshot:
    opened = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minute)
    values: dict[str, object] = {
        "symbol": "BTCUSDT", "timeframe": "1m", "candle_open_time": opened,
        "candle_close_time": opened + timedelta(minutes=1) - timedelta(milliseconds=1),
        "close": Decimal("110"), "ema_9": Decimal("105"), "ema_21": Decimal("100"),
        "rsi_14": Decimal("60"), "atr_14": Decimal("0.5"), "vwap": Decimal("100"),
        "volume": Decimal("20"), "volume_ma_20": Decimal("10"), "is_ready": True,
        "calculated_at": opened + timedelta(minutes=1),
    }
    values.update(updates)
    return IndicatorSnapshot(**values)


def feed_status(state: FeedState = FeedState.CONNECTED) -> MarketFeedStatus:
    return MarketFeedStatus(
        exchange="binance", status=state, timeframe="1m",
        symbols={"BTCUSDT": SymbolFeedStatus(status=state)},
    )


def test_strategy_long_short_and_no_trade_rules() -> None:
    async def exercise() -> None:
        engine = StrategyEngine(Settings(), market_status_provider=feed_status)
        long_signal = await engine.process_snapshot(ready_snapshot())
        assert long_signal is not None
        assert long_signal.direction == SignalDirection.LONG
        assert long_signal.score == 100
        assert long_signal.confidence == 1
        assert long_signal.is_actionable
        assert long_signal.context.close == Decimal("110")

        short = ready_snapshot(1, close=Decimal("90"), ema_9=Decimal("95"), ema_21=Decimal("100"), rsi_14=Decimal("40"), vwap=Decimal("100"))
        short_signal = await engine.process_snapshot(short)
        assert short_signal is not None
        assert short_signal.direction == SignalDirection.SHORT
        assert short_signal.is_actionable

        insufficient_volume = await engine.process_snapshot(ready_snapshot(2, volume=Decimal("5")))
        assert insufficient_volume is not None
        assert insufficient_volume.direction == SignalDirection.NO_TRADE
        assert insufficient_volume.score == 80
        assert not insufficient_volume.is_actionable
        assert "Volume ratio below confirmation threshold" in insufficient_volume.reasons

        not_ready = await engine.process_snapshot(ready_snapshot(3, is_ready=False))
        assert not_ready is not None
        assert not_ready.direction == SignalDirection.NO_TRADE
        assert not_ready.reasons == ("Indicators not ready",)
    asyncio.run(exercise())


def test_strategy_stale_idempotency_and_symbol_isolation() -> None:
    async def exercise() -> None:
        stale_engine = StrategyEngine(Settings(), market_status_provider=lambda: feed_status(FeedState.STALE))
        stale = await stale_engine.process_snapshot(ready_snapshot())
        assert stale is not None and stale.direction == SignalDirection.NO_TRADE
        assert stale.reasons == ("Market data is stale",)

        other_symbol_stale = MarketFeedStatus(
            exchange="binance", status=FeedState.STALE, timeframe="1m",
            symbols={"BTCUSDT": SymbolFeedStatus(status=FeedState.CONNECTED), "ETHUSDT": SymbolFeedStatus(status=FeedState.STALE)},
        )
        isolated_feed = StrategyEngine(Settings(), market_status_provider=lambda: other_symbol_stale)
        assert (await isolated_feed.process_snapshot(ready_snapshot())).direction == SignalDirection.LONG

        engine = StrategyEngine(Settings(), market_status_provider=feed_status)
        first = ready_snapshot(0)
        assert await engine.process_snapshot(first) is not None
        assert await engine.process_snapshot(first) is None
        assert await engine.process_snapshot(ready_snapshot(-1)) is None
        eth = ready_snapshot(0, symbol="ETHUSDT")
        assert await engine.process_snapshot(eth) is not None
        assert (await engine.latest("ETHUSDT")).symbol == "ETHUSDT"
        assert len(await engine.history("BTCUSDT", 10)) == 1
    asyncio.run(exercise())


def test_strategy_configuration_validation() -> None:
    with pytest.raises(ValueError, match="rsi_long_min"):
        Settings(rsi_long_min=68, rsi_long_max=68)
    with pytest.raises(ValueError, match="min_atr_bps"):
        Settings(min_atr_bps=20, max_atr_bps=10)


def test_strategy_rest_endpoints_and_websocket_event_serialization() -> None:
    with TestClient(app) as client:
        response = client.get("/api/strategy/BTCUSDT")
        assert response.status_code == 200
        assert response.json()["direction"] == "no_trade"
        assert response.json()["is_actionable"] is False
        assert client.get("/api/strategy/status").status_code == 200
        assert client.get("/api/strategy/BTCUSDT/history?limit=10").json() == []
        assert client.get("/api/strategy/DOGEUSDT").status_code == 404
    event = {"type": "strategy.signal", "data": ready_snapshot().model_dump(mode="json")}
    assert event["type"] == "strategy.signal"
    assert event["data"]["close"] == "110"
