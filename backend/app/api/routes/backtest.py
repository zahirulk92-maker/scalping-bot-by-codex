"""Simulation-only historical backtest endpoints; no exchange execution is possible."""

from fastapi import APIRouter, HTTPException, Query, Request

from app.backtest.engine import BacktestEngine
from app.backtest.models import BacktestRequest

router = APIRouter(tags=["backtest"])


def engine(request: Request) -> BacktestEngine:
    return request.app.state.backtest_engine


@router.post("/api/backtest/run")
async def run_backtest(payload: BacktestRequest, request: Request) -> dict[str, object]:
    limiter = request.app.state.request_rate_limiter
    client = request.client.host if request.client else "unknown"
    guard = request.app.state.heavy_job_guard.backtests
    if not limiter.allow(f"backtest:{client}"):
        raise HTTPException(status_code=429, detail="backtest rate limit exceeded")
    if guard.locked():
        raise HTTPException(status_code=429, detail="a backtest is already running")
    await guard.acquire()
    try:
        return (await engine(request).run(payload)).model_dump(mode="json")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        guard.release()


@router.get("/api/backtest")
async def recent_backtests(request: Request) -> list[dict[str, object]]:
    return [result.model_dump(mode="json", exclude={"trades", "equity_curve"}) for result in engine(request).store.recent()]


@router.get("/api/backtest/{run_id}")
async def backtest_result(run_id: str, request: Request) -> dict[str, object]:
    result = engine(request).store.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="unknown backtest run")
    return result.model_dump(mode="json", exclude={"trades", "equity_curve"})


@router.get("/api/backtest/{run_id}/trades")
async def backtest_trades(run_id: str, request: Request, limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0)) -> list[dict[str, object]]:
    result = engine(request).store.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="unknown backtest run")
    return [trade.model_dump(mode="json") for trade in result.trades[offset:offset + limit]]


@router.get("/api/backtest/{run_id}/equity")
async def backtest_equity(run_id: str, request: Request) -> list[dict[str, object]]:
    result = engine(request).store.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="unknown backtest run")
    return [point.model_dump(mode="json") for point in result.equity_curve]
