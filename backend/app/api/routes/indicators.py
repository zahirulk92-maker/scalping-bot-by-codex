"""Read-only indicator snapshots for the monitoring dashboard."""

from fastapi import APIRouter, HTTPException, Query, Request

from app.indicators.engine import IndicatorEngine

router = APIRouter(tags=["indicators"])


def engine(request: Request) -> IndicatorEngine:
    return request.app.state.indicator_engine


@router.get("/api/indicators/status")
async def indicator_status(request: Request) -> dict[str, dict[str, bool]]:
    return await engine(request).readiness()


@router.get("/api/indicators/{symbol}/history")
async def indicator_history(symbol: str, request: Request, limit: int = Query(default=500, ge=1, le=500)) -> list[dict[str, object]]:
    normalized = symbol.upper()
    if normalized not in engine(request).settings.symbols:
        raise HTTPException(status_code=404, detail="unknown configured symbol")
    return [snapshot.model_dump(mode="json") for snapshot in await engine(request).history(normalized, limit)]


@router.get("/api/indicators/{symbol}")
async def indicator_snapshot(symbol: str, request: Request) -> dict[str, object]:
    normalized = symbol.upper()
    if normalized not in engine(request).settings.symbols:
        raise HTTPException(status_code=404, detail="unknown configured symbol")
    return (await engine(request).latest(normalized)).model_dump(mode="json")
