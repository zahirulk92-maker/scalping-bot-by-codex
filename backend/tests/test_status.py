from fastapi.testclient import TestClient

from app.main import app


def test_status_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {
        "mode": "paper", "starting_balance": 100.0, "currency": "USDT",
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"], "timeframe": "1m",
        "risk_per_trade": 0.005, "max_daily_loss": 0.03, "max_open_positions": 1,
    }
