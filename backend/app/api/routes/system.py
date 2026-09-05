"""Operational health and safe database-status endpoints."""

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.tools.export import render_records

router = APIRouter(tags=["system"])


@router.get("/api/system/health")
async def system_health(request: Request) -> dict[str, object]:
    return request.app.state.monitoring_service.health().model_dump(mode="json")


@router.get("/api/system/database")
async def database_status(request: Request) -> dict[str, object]:
    return request.app.state.paper_repository.database_status()


@router.get("/api/system/alerts")
async def active_alerts(request: Request) -> list[dict[str, object]]:
    session = request.app.state.paper_session
    return [item.model_dump(mode="json") for item in request.app.state.paper_repository.active_alerts(session.session_id)]


@router.get("/api/system/live")
async def liveness(request: Request) -> dict[str, object]:
    return {"status": "live", "uptime_seconds": int((datetime.now(UTC) - request.app.state.started_at).total_seconds())}


@router.get("/api/system/ready")
async def readiness(request: Request) -> dict[str, object]:
    health = request.app.state.monitoring_service.health()
    ready = health.database.value == "healthy" and health.recovery.value == "complete" and health.overall.value != "error"
    return {"status": "ready" if ready else "not_ready", "degraded": health.overall.value == "degraded", "health": health.model_dump(mode="json")}


@router.get("/api/system/version")
async def version(request: Request) -> dict[str, object]:
    settings = request.app.state.session_settings
    return {"version": settings.app_version, "environment": settings.app_env, "build_commit": settings.build_commit or None, "build_timestamp": settings.build_timestamp or None}


@router.get("/api/system/diagnostics")
async def diagnostics(request: Request) -> dict[str, object]:
    settings = request.app.state.session_settings
    return {"environment": settings.app_env, "trading_mode": settings.trading_mode, "execution_mode": settings.execution_mode, "strategy_profile": settings.strategy_profile, "symbols": settings.symbols, "timeframe": settings.default_timeframe, "market_exchange": settings.market_exchange, "risk_per_trade": settings.risk_per_trade, "max_daily_loss": settings.max_daily_loss, "database": request.app.state.paper_repository.database_status()}


@router.get("/api/system/metrics")
async def metrics(request: Request) -> dict[str, object]:
    market = request.app.state.market_service
    monitoring = request.app.state.monitoring_service
    return {"market_messages_received": market.messages_received, "valid_candles": market.valid_candles, "invalid_candles": market.invalid_candles, "market_reconnects": market.reconnect_count, "active_ws_clients": len(market._clients), **monitoring.counters}


@router.get("/api/system/exports/{kind}")
async def download_export(kind: str, request: Request, format: str = "json") -> Response:
    """Download operational CSV/JSON; research exports are intentionally runtime-only."""
    if format not in {"json", "csv"}:
        raise HTTPException(status_code=422, detail="format must be json or csv")
    if kind == "backtest-summaries":
        rows = [result.model_dump(mode="json", exclude={"trades", "equity_curve"}) for result in request.app.state.backtest_engine.store.recent()]
    elif kind == "optimization-summaries":
        rows = [{"run_id": run.run_id, "created_at": run.created_at, "symbols": run.symbols, "timeframe": run.timeframe, "selected_candidate_id": run.selected_candidate_id, "selection_reason": run.selection_reason, "candidate_count": len(run.candidates), "invalid_candidate_count": len(run.invalid_candidates), "final_holdout_evaluated": run.final_holdout_evaluated} for run in request.app.state.optimization_engine.store.recent()]
    elif kind == "monitoring-metrics":
        monitoring = request.app.state.monitoring_service
        rows = [{"health": monitoring.health().model_dump(mode="json"), "counters": monitoring.counters, "freshness": monitoring.freshness}]
    elif kind in {"paper-trades", "daily-metrics", "alerts"}:
        table = {"paper-trades": "paper_trades", "daily-metrics": "daily_metrics", "alerts": "alerts"}[kind]
        with request.app.state.paper_repository.database.connection() as connection:
            raw_rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
        rows = [{key: json.loads(value) if key == "data" else value for key, value in row.items()} for row in raw_rows]
    else:
        raise HTTPException(status_code=404, detail="unknown export kind")
    contents, media_type = render_records(rows, format)
    return Response(content=contents, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{kind}.{format}"'})
