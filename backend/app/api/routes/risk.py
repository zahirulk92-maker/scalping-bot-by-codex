"""Read-only trade-plan risk endpoints; no orders or account API access."""

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, Request

from app.risk.engine import RiskEngine

router = APIRouter(tags=["risk"])


def engine(request: Request) -> RiskEngine:
    return request.app.state.risk_engine


@router.get("/api/risk/status")
async def risk_status(request: Request) -> dict[str, object]:
    risk = engine(request)
    account = await risk.account_state()
    settings = risk.settings
    risk_amount = account.current_equity * Decimal(str(settings.risk_per_trade))
    max_daily_loss = account.current_equity * Decimal(str(settings.max_daily_loss))
    return {
        "equity": account.current_equity, "risk_per_trade": Decimal(str(settings.risk_per_trade)),
        "risk_per_trade_usdt": risk_amount, "max_daily_loss": Decimal(str(settings.max_daily_loss)),
        "max_daily_loss_usdt": max_daily_loss, "realized_pnl_today": account.realized_pnl_today,
        "daily_loss_used": account.daily_loss_used, "open_positions": account.open_position_count,
        "max_open_positions": settings.max_open_positions, "execution_enabled": False,
    }


@router.get("/api/risk/{symbol}/history")
async def risk_history(symbol: str, request: Request, limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, object]]:
    normalized = symbol.upper()
    if normalized not in engine(request).settings.symbols:
        raise HTTPException(status_code=404, detail="unknown configured symbol")
    return [plan.model_dump(mode="json") for plan in await engine(request).history(normalized, limit)]


@router.get("/api/risk/{symbol}")
async def risk_plan(symbol: str, request: Request) -> dict[str, object]:
    normalized = symbol.upper()
    if normalized not in engine(request).settings.symbols:
        raise HTTPException(status_code=404, detail="unknown configured symbol")
    return (await engine(request).latest(normalized)).model_dump(mode="json")
