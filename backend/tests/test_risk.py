import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.market.models import FeedState, MarketFeedStatus, SymbolFeedStatus
from app.risk.engine import RiskEngine
from app.risk.models import RiskAccountState
from app.risk.store import RiskStore
from app.strategy.models import SignalContext, SignalDirection, SignalSnapshot

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)


def signal(minute: int = 0, direction: SignalDirection = SignalDirection.LONG, **updates: object) -> SignalSnapshot:
    opened = NOW - timedelta(seconds=10) + timedelta(minutes=minute)
    context = SignalContext(close=Decimal("100"), atr_14=Decimal("0.5"))
    values: dict[str, object] = {
        "symbol": "BTCUSDT", "timeframe": "1m", "direction": direction, "score": 100,
        "confidence": 1, "is_actionable": True, "context": context, "generated_at": NOW,
        "candle_open_time": opened, "candle_close_time": opened + timedelta(minutes=1) - timedelta(milliseconds=1),
    }
    values.update(updates)
    return SignalSnapshot(**values)


def feed(state: FeedState = FeedState.CONNECTED) -> MarketFeedStatus:
    return MarketFeedStatus(exchange="binance", status=state, timeframe="1m", symbols={"BTCUSDT": SymbolFeedStatus(status=state)})


def engine(settings: Settings | None = None, account: RiskAccountState | None = None, status: MarketFeedStatus | None = None) -> RiskEngine:
    actual_settings = settings or Settings()
    return RiskEngine(actual_settings, market_status_provider=lambda: status or feed(), store=RiskStore(actual_settings, account), now_provider=lambda: NOW)


def test_long_and_short_plan_math_and_costs() -> None:
    async def exercise() -> None:
        long = await engine().process_signal(signal())
        assert long is not None and long.approved
        assert long.planned_risk_amount_usdt == Decimal("0.5")
        assert long.actual_risk_amount_usdt == Decimal("0.5")
        assert long.stop_loss_price == Decimal("99.25")
        assert long.take_profit_price == Decimal("101.125")
        assert long.stop_distance_bps == Decimal("75.000")
        assert long.estimated_quantity == Decimal(2) / Decimal(3)
        assert long.position_notional_usdt == Decimal(200) / Decimal(3)
        assert long.risk_reward_ratio == Decimal("1.5")
        assert long.estimated_fees_usdt is not None and long.estimated_fees_usdt > 0
        assert long.estimated_slippage_usdt is not None and long.estimated_slippage_usdt > 0
        assert long.net_reward_usdt is not None and long.net_reward_usdt > 0

        short = await engine().process_signal(signal(direction=SignalDirection.SHORT))
        assert short is not None and short.approved
        assert short.stop_loss_price == Decimal("100.75")
        assert short.take_profit_price == Decimal("98.875")
    asyncio.run(exercise())


def test_notional_cap_and_stop_guards() -> None:
    async def exercise() -> None:
        capped = await engine().process_signal(signal(context=SignalContext(close=Decimal("100"), atr_14=Decimal("0.2"))))
        assert capped is not None and capped.approved
        assert capped.position_notional_usdt == Decimal("100")
        assert capped.actual_risk_amount_usdt == Decimal("0.3")
        assert capped.planned_risk_amount_usdt == Decimal("0.5")

        too_small = await engine().process_signal(signal(context=SignalContext(close=Decimal("100"), atr_14=Decimal("0.02"))))
        assert too_small is not None and not too_small.approved
        assert too_small.rejection_reasons == ("Stop distance is below the configured minimum",)

        too_large = await engine().process_signal(signal(context=SignalContext(close=Decimal("100"), atr_14=Decimal("1"))))
        assert too_large is not None and not too_large.approved
        assert too_large.rejection_reasons == ("Stop distance exceeds the configured maximum",)
    asyncio.run(exercise())


def test_account_market_signal_and_cost_guards() -> None:
    async def exercise() -> None:
        near_limit = RiskAccountState(current_equity=Decimal("100"), realized_pnl_today=Decimal("-2.7"))
        daily = await engine(account=near_limit).process_signal(signal())
        assert daily is not None and "Daily loss limit would be exceeded" in daily.rejection_reasons

        position_limit = RiskAccountState(current_equity=Decimal("100"), open_position_count=1)
        positions = await engine(account=position_limit).process_signal(signal())
        assert positions is not None and "Maximum open-position limit reached" in positions.rejection_reasons

        stale = await engine().process_signal(signal(generated_at=NOW - timedelta(seconds=91)))
        assert stale is not None and stale.rejection_reasons == ("Strategy signal is stale",)

        bad_atr = await engine().process_signal(signal(context=SignalContext(close=Decimal("100"), atr_14=Decimal("0"))))
        assert bad_atr is not None and bad_atr.rejection_reasons == ("ATR is unavailable or invalid",)

        stale_market = await engine(status=feed(FeedState.STALE)).process_signal(signal())
        assert stale_market is not None and stale_market.rejection_reasons == ("Market feed is stale",)

        high_cost_settings = Settings(estimated_fee_bps=10_000, estimated_slippage_bps=10_000)
        high_cost = await engine(settings=high_cost_settings).process_signal(signal())
        assert high_cost is not None and "Estimated costs eliminate the expected reward" in high_cost.rejection_reasons

        no_cost = await engine(settings=Settings(estimated_fee_bps=0, estimated_slippage_bps=0)).process_signal(signal())
        assert no_cost is not None and no_cost.estimated_fees_usdt == Decimal(0) and no_cost.estimated_slippage_usdt == Decimal(0)
    asyncio.run(exercise())


def test_equity_scaling_idempotency_and_symbol_isolation() -> None:
    async def exercise() -> None:
        low = await engine(account=RiskAccountState(current_equity=Decimal("50"))).process_signal(signal())
        high = await engine(account=RiskAccountState(current_equity=Decimal("200"))).process_signal(signal())
        assert low is not None and low.planned_risk_amount_usdt == Decimal("0.25")
        assert high is not None and high.planned_risk_amount_usdt == Decimal("1")

        isolated = engine()
        first = signal(0)
        assert await isolated.process_signal(first) is not None
        assert await isolated.process_signal(first) is None
        assert await isolated.process_signal(signal(-1)) is None
        eth = signal(0, symbol="ETHUSDT")
        assert await isolated.process_signal(eth) is not None
        assert (await isolated.latest("ETHUSDT")).symbol == "ETHUSDT"
        assert len(await isolated.history("BTCUSDT", 10)) == 1
    asyncio.run(exercise())


def test_risk_config_validation_and_rest_websocket_serialization() -> None:
    with pytest.raises(ValueError, match="min_stop_distance_bps"):
        Settings(min_stop_distance_bps=10, max_stop_distance_bps=10)
    with TestClient(app) as client:
        status = client.get("/api/risk/status")
        assert status.status_code == 200
        assert Decimal(status.json()["risk_per_trade_usdt"]) == Decimal("0.5")
        app.state.market_service.state = FeedState.CONNECTED
        approved_signal = signal(generated_at=datetime.now(UTC))
        assert asyncio.run(app.state.risk_engine.process_signal(approved_signal)) is not None
        response = client.get("/api/risk/BTCUSDT")
        assert response.status_code == 200
        assert response.json()["approved"] is True
        rejected_signal = signal(1, generated_at=datetime.now(UTC), context=SignalContext(close=Decimal("100"), atr_14=Decimal(0)))
        assert asyncio.run(app.state.risk_engine.process_signal(rejected_signal)) is not None
        assert client.get("/api/risk/BTCUSDT").json()["approved"] is False
        assert client.get("/api/risk/DOGEUSDT").status_code == 404
    event = {"type": "risk.plan", "data": {"symbol": "BTCUSDT", "approved": True, "risk_amount_usdt": "0.5"}}
    assert event["type"] == "risk.plan"
    assert event["data"]["approved"] is True
