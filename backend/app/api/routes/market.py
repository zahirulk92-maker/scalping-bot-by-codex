"""Read-only market data endpoints for the monitoring dashboard."""

from fastapi import APIRouter, HTTPException, Query, Request

from app.market.service import MarketDataService

router = APIRouter(tags=["market"])


def get_market_service(request: Request) -> MarketDataService:
    return request.app.state.market_service


@router.get("/api/market/status")
async def market_status(request: Request) -> dict[str, object]:
    return get_market_service(request).status_snapshot().model_dump(mode="json")


@router.get("/api/market/{symbol}/candles")
async def market_candles(
    symbol: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    service = get_market_service(request)
    normalized = symbol.upper()
    if normalized not in service.settings.symbols:
        raise HTTPException(status_code=404, detail="unknown configured symbol")
    candles = await service.store.get_recent_candles(normalized, service.settings.default_timeframe, limit)
    return [candle.model_dump(mode="json") for candle in candles]
