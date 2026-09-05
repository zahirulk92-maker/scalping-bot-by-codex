from fastapi import APIRouter, Depends

from app.config import Settings, get_settings

router = APIRouter(tags=["foundation"])


@router.get("/api/status")
def status(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Expose the non-sensitive paper foundation configuration."""
    return {
        "mode": settings.trading_mode,
        "starting_balance": settings.starting_balance,
        "currency": "USDT",
        "symbols": settings.symbols,
        "timeframe": settings.default_timeframe,
        "risk_per_trade": settings.risk_per_trade,
        "max_daily_loss": settings.max_daily_loss,
        "max_open_positions": settings.max_open_positions,
    }
