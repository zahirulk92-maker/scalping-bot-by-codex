import pytest
from pydantic import ValidationError

from app.config import Settings


def test_valid_configuration() -> None:
    settings = Settings()
    assert settings.trading_mode == "paper"
    assert settings.symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


@pytest.mark.parametrize("mode", ["live", "", "unknown"])
def test_invalid_trading_mode(mode: str) -> None:
    with pytest.raises(ValidationError):
        Settings(trading_mode=mode)


def test_live_mode_rejected() -> None:
    with pytest.raises(ValidationError, match="only trading mode"):
        Settings(trading_mode="live")


@pytest.mark.parametrize("field, value", [("starting_balance", 0), ("risk_per_trade", 0), ("max_daily_loss", 1.1)])
def test_invalid_risk_configuration(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_empty_symbols() -> None:
    with pytest.raises(ValidationError):
        Settings(symbols=[])


def test_comma_separated_symbols_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYMBOLS", "BTCUSDT,ETHUSDT")
    assert Settings().symbols == ["BTCUSDT", "ETHUSDT"]


def test_invalid_market_exchange_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(market_exchange="unsupported")


def test_invalid_indicator_period_relationship_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(ema_fast_period=21, ema_slow_period=9)
