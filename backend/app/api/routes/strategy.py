"""Read-only strategy signal endpoints; this module never executes orders."""

from fastapi import APIRouter, HTTPException, Query, Request

from app.strategy.engine import StrategyEngine

router = APIRouter(tags=["strategy"])


def engine(request: Request) -> StrategyEngine:
    return request.app.state.strategy_engine


@router.get("/api/strategy/status")
async def strategy_status(request: Request) -> dict[str, dict[str, object]]:
    return await engine(request).readiness()


@router.get("/api/strategy/{symbol}/history")
async def strategy_history(symbol: str, request: Request, limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, object]]:
    normalized = symbol.upper()
    if normalized not in engine(request).settings.symbols:
        raise HTTPException(status_code=404, detail="unknown configured symbol")
    return [signal.model_dump(mode="json") for signal in await engine(request).history(normalized, limit)]


@router.get("/api/strategy/{symbol}")
async def strategy_signal(symbol: str, request: Request) -> dict[str, object]:
    normalized = symbol.upper()
    if normalized not in engine(request).settings.symbols:
        raise HTTPException(status_code=404, detail="unknown configured symbol")
    return (await engine(request).latest(normalized)).model_dump(mode="json")
