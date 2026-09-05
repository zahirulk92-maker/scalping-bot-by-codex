"""Research-only optimization endpoints; they cannot alter live or paper settings."""

from fastapi import APIRouter, HTTPException, Request

from app.optimization.engine import OptimizationEngine
from app.optimization.models import OptimizationRequest

router = APIRouter(tags=["optimization"])


def engine(request: Request) -> OptimizationEngine:
    return request.app.state.optimization_engine


@router.post("/api/optimization/run")
async def run_optimization(payload: OptimizationRequest, request: Request) -> dict[str, object]:
    limiter = request.app.state.request_rate_limiter
    client = request.client.host if request.client else "unknown"
    guard = request.app.state.heavy_job_guard.optimizations
    if not limiter.allow(f"optimization:{client}"):
        raise HTTPException(status_code=429, detail="optimization rate limit exceeded")
    if guard.locked():
        raise HTTPException(status_code=429, detail="an optimization is already running")
    await guard.acquire()
    try:
        return (await engine(request).run(payload)).model_dump(mode="json")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        guard.release()


@router.get("/api/optimization")
async def list_optimizations(request: Request) -> list[dict[str, object]]:
    return [run.model_dump(mode="json") for run in engine(request).store.recent()]


@router.get("/api/optimization/{run_id}")
async def get_optimization(run_id: str, request: Request) -> dict[str, object]:
    result = engine(request).store.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="optimization run not found")
    return result.model_dump(mode="json")


@router.post("/api/optimization/{run_id}/final-evaluate")
async def final_evaluate(run_id: str, request: Request) -> dict[str, object]:
    try:
        return (await engine(request).final_evaluate(run_id)).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(status_code=404, detail="optimization run not found") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
