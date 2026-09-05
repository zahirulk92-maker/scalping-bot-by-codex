"""Read-only paper-simulation state endpoints; no command endpoints exist."""

from fastapi import APIRouter, Query, Request

from app.execution.paper_engine import PaperExecutionEngine

router = APIRouter(tags=["paper"])


def engine(request: Request) -> PaperExecutionEngine:
    return request.app.state.paper_execution_engine


@router.get("/api/paper/account")
async def paper_account(request: Request) -> dict[str, object]:
    return (await engine(request).account()).model_dump(mode="json")


@router.get("/api/paper/positions")
async def paper_positions(request: Request) -> list[dict[str, object]]:
    return [position.model_dump(mode="json") for position in await engine(request).positions()]


@router.get("/api/paper/trades")
async def paper_trades(request: Request, limit: int = Query(default=100, ge=1, le=1000)) -> list[dict[str, object]]:
    return [trade.model_dump(mode="json") for trade in await engine(request).trades(limit)]


@router.get("/api/paper/session")
async def paper_session(request: Request) -> dict[str, object]:
    return request.app.state.paper_session.model_dump(mode="json")


@router.get("/api/paper/metrics")
async def paper_metrics(request: Request) -> dict[str, object]:
    session = request.app.state.paper_session
    return request.app.state.paper_repository.metrics(session).model_dump(mode="json")


@router.get("/api/paper/metrics/daily")
async def paper_daily_metrics(request: Request, limit: int = Query(default=30, ge=1, le=365)) -> list[dict[str, object]]:
    session = request.app.state.paper_session
    return [metric.model_dump(mode="json") for metric in request.app.state.paper_repository.daily_metrics(session.session_id, limit)]


@router.get("/api/paper/metrics/equity")
async def paper_equity_metrics(request: Request, limit: int = Query(default=1000, ge=1, le=5000)) -> list[dict[str, str]]:
    session = request.app.state.paper_session
    return request.app.state.paper_repository.equity_curve(session.session_id, limit)


@router.get("/api/paper/metrics/symbols")
async def paper_symbol_metrics(request: Request) -> list[dict[str, object]]:
    session = request.app.state.paper_session
    return [metric.model_dump(mode="json") for metric in request.app.state.paper_repository.symbol_metrics(session.session_id, request.app.state.session_settings.symbols)]


@router.get("/api/paper/audit")
async def paper_audit(request: Request, limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)) -> list[dict[str, object]]:
    session = request.app.state.paper_session
    return request.app.state.paper_repository.audit(session.session_id, limit, offset)
