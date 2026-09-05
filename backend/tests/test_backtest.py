import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.backtest.analytics import performance_slice
from app.backtest.engine import BacktestEngine
from app.backtest.models import BacktestRequest, BacktestTrade
from app.config import Settings
from app.execution.models import ExitReason
from app.main import app
from app.market.models import Candle
from app.strategy.models import SignalDirection

START = datetime(2026, 1, 1, tzinfo=UTC)


def candles(symbol: str, count: int = 8) -> list[Candle]:
    values = ["100", "99", "100", "101", "100", "101", "102", "101"]
    result = []
    for index, value in enumerate(values[:count]):
        opened = START + timedelta(minutes=index)
        price = Decimal(value)
        result.append(Candle(symbol=symbol, timeframe="1m", open_time=opened, close_time=opened + timedelta(minutes=1) - timedelta(milliseconds=1), open=price, high=price + 1, low=price - 1, close=price, volume=Decimal("10"), is_closed=True))
    return result


def test_replay_is_chronological_bounded_and_reproducible() -> None:
    async def exercise() -> None:
        settings = Settings(ema_fast_period=2, ema_slow_period=3, rsi_period=2, atr_period=2, volume_ma_period=2)
        request = BacktestRequest(symbols=["BTCUSDT"], start_time=START, end_time=START + timedelta(minutes=8))
        first = await BacktestEngine(settings).run(request, {"BTCUSDT": candles("BTCUSDT")})
        second = await BacktestEngine(settings).run(request, {"BTCUSDT": candles("BTCUSDT")})
        assert [point.timestamp for point in first.equity_curve] == sorted(point.timestamp for point in first.equity_curve)
        assert len(first.equity_curve) == 8
        assert first.net_pnl == second.net_pnl and first.total_trades == second.total_trades
        assert first.starting_balance == Decimal("100.0")
    asyncio.run(exercise())


def test_analytics_zero_and_known_trade_metrics() -> None:
    empty = performance_slice([])
    assert empty.trades == 0 and empty.profit_factor is None and empty.average_r is None
    trade = BacktestTrade(symbol="BTCUSDT", direction=SignalDirection.LONG, entry_time=START, entry_price=Decimal("100"), exit_time=START + timedelta(minutes=1), exit_price=Decimal("101"), exit_reason=ExitReason.TAKE_PROFIT, quantity=Decimal(1), planned_risk_amount=Decimal("0.5"), gross_pnl=Decimal("1"), fees=Decimal("0.1"), net_pnl=Decimal("0.9"), r_multiple=Decimal("1.8"))
    metrics = performance_slice([trade])
    assert metrics.trades == 1 and metrics.wins == 1 and metrics.net_pnl == Decimal("0.9") and metrics.average_r == Decimal("1.8")


def test_backtest_rest_result_trades_equity_and_validation() -> None:
    async def fake_load(symbol: str, *_: object) -> list[Candle]:
        return candles(symbol)

    with TestClient(app) as client:
        app.state.backtest_engine.loader.load = fake_load
        payload = {"symbols": ["BTCUSDT"], "timeframe": "1m", "start_time": START.isoformat(), "end_time": (START + timedelta(minutes=8)).isoformat()}
        response = client.post("/api/backtest/run", json=payload)
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        assert client.get(f"/api/backtest/{run_id}").status_code == 200
        assert client.get(f"/api/backtest/{run_id}/trades?limit=10&offset=0").status_code == 200
        assert len(client.get(f"/api/backtest/{run_id}/equity").json()) == 8
        assert client.get("/api/backtest/missing").status_code == 404
        assert client.post("/api/backtest/run", json={**payload, "end_time": START.isoformat()}).status_code == 422
        assert client.post("/api/backtest/run", json={**payload, "symbols": ["DOGEUSDT"]}).status_code == 422
