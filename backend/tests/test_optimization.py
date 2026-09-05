from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.market.models import Candle
from app.optimization.engine import OptimizationEngine
from app.optimization.models import OptimizationRequest


START = datetime(2026, 1, 1, tzinfo=UTC)


def candles(symbol: str) -> list[Candle]:
    return [
        Candle(
            symbol=symbol, timeframe="1m", open_time=START + timedelta(minutes=index),
            close_time=START + timedelta(minutes=index + 1) - timedelta(milliseconds=1),
            open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
            volume=Decimal("10"), is_closed=True,
        )
        for index in range(8)
    ]


def test_candidate_settings_revalidate_cross_field_constraints() -> None:
    optimizer = OptimizationEngine(Settings())
    with pytest.raises(ValueError):
        optimizer._candidate_settings({"EMA_FAST_PERIOD": 30, "EMA_SLOW_PERIOD": 20})


def test_chronological_split_preserves_holdout() -> None:
    request = OptimizationRequest(symbols=["BTCUSDT"], start_time=START, end_time=START + timedelta(days=10))
    train_end, validation_end = OptimizationEngine._split_times(request)
    assert train_end == START + timedelta(days=6)
    assert validation_end == START + timedelta(days=8)
    assert validation_end < request.end_time


def test_optimization_rest_baseline_never_selects_holdout() -> None:
    async def fake_load(symbol: str, *_: object):
        return candles(symbol)

    with TestClient(app) as client:
        app.state.optimization_engine.backtest_engine.loader.load = fake_load
        payload = {"symbols": ["BTCUSDT"], "timeframe": "1m", "start_time": START.isoformat(), "end_time": (START + timedelta(minutes=8)).isoformat(), "parameter_grid": {"EMA_FAST_PERIOD": [8]}}
        response = client.post("/api/optimization/run", json=payload)
        assert response.status_code == 200
        result = response.json()
        assert result["baseline"]["is_baseline"] is True
        assert result["candidates"][0]["parameters"] == {"EMA_FAST_PERIOD": 8}
        assert result["selected_candidate_id"] is None
        assert result["final_holdout_evaluated"] is False
        assert client.post(f"/api/optimization/{result['run_id']}/final-evaluate").status_code == 422
