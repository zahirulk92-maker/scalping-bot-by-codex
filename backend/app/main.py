"""FastAPI entry point for the Phase 1 foundation."""

import asyncio
import logging
from datetime import UTC, datetime
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.health import router as health_router
from app.api.routes.indicators import router as indicators_router
from app.api.routes.market import router as market_router
from app.api.routes.market_ws import router as market_ws_router
from app.api.routes.status import router as status_router
from app.api.routes.risk import router as risk_router
from app.api.routes.paper import router as paper_router
from app.api.routes.backtest import router as backtest_router
from app.api.routes.system import router as system_router
from app.backtest.engine import BacktestEngine
from app.api.routes.optimization import router as optimization_router
from app.optimization.engine import OptimizationEngine
from app.db.database import Database
from app.db.models import AlertSeverity
from app.db.repositories.paper import PaperRepository
from app.monitoring.service import MonitoringService
from app.config import get_settings
from app.core.logger import configure_logging
from app.core.logger import request_id_context
from app.core.exceptions import BotError
from app.core.operations import HeavyJobGuard, RequestRateLimiter
from app.indicators.engine import IndicatorEngine
from app.indicators.models import IndicatorSnapshot
from app.market.service import MarketDataService
from app.risk.engine import RiskEngine
from app.risk.models import TradePlan
from app.execution.paper_engine import PaperExecutionEngine
from app.strategy.models import SignalSnapshot
from app.strategy.engine import StrategyEngine
from app.api.routes.strategy import router as strategy_router
from app.api.routes.validation import router as validation_router
from app.validation.engine import ValidationEngine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    configure_logging(Path(__file__).resolve().parents[1] / "logs", settings.log_format)
    database = Database(settings)
    database.initialize()
    repository = PaperRepository(database)
    pruned_alerts = repository.prune_resolved_alerts(settings.alert_retention_days)
    if pruned_alerts:
        logger.info("Pruned %s resolved alerts past retention", pruned_alerts)
    session, session_settings, resumed = repository.resume_or_create_session(settings)
    logger.info("========================================")
    logger.info("SCALPING BOT")
    logger.info("Phase: FORWARD PAPER TESTING | Mode: %s", session_settings.trading_mode.upper())
    logger.info("Environment: %s | Database: SQLite | Market: %s | Execution: %s", session_settings.app_env, session_settings.market_exchange, session_settings.execution_mode)
    logger.info("Session %s %s; profile=%s", "resumed" if resumed else "created", session.session_id, session.strategy_profile)
    logger.info("Starting Balance: %s USDT | Symbols: %s", session_settings.starting_balance, ", ".join(session_settings.symbols))
    logger.info("Timeframe: %s | Risk Per Trade: %.2f%%", session_settings.default_timeframe, session_settings.risk_per_trade * 100)
    logger.info("Daily Loss Limit: %.2f%% | Max Open Positions: %s", session_settings.max_daily_loss * 100, session_settings.max_open_positions)
    logger.info("Live Trading: DISABLED")
    logger.info("========================================")
    application.state.paper_repository = repository
    application.state.started_at = datetime.now(UTC)
    application.state.heavy_job_guard = HeavyJobGuard(session_settings.max_concurrent_backtests, session_settings.max_concurrent_optimizations)
    application.state.request_rate_limiter = RequestRateLimiter(session_settings.heavy_request_limit_per_minute)
    application.state.paper_session = session
    application.state.session_settings = session_settings
    application.state.indicator_engine = IndicatorEngine(session_settings)
    application.state.backtest_engine = BacktestEngine(session_settings)
    application.state.optimization_engine = OptimizationEngine(session_settings, application.state.backtest_engine)
    application.state.market_service = MarketDataService(session_settings, on_closed_candle=application.state.indicator_engine.process_candle)
    application.state.risk_engine = RiskEngine(
        session_settings,
        market_status_provider=application.state.market_service.status_snapshot,
    )
    application.state.paper_execution_engine = PaperExecutionEngine(
        session_settings,
        market_status_provider=application.state.market_service.status_snapshot,
        risk_account_sink=application.state.risk_engine.store.replace_account_state,
        on_event=None,
        repository=repository,
        session_id=session.session_id,
    )
    application.state.market_service.set_market_candle_handler(application.state.paper_execution_engine.process_market_candle)
    account, positions, trades = repository.load_state(session.session_id)
    await application.state.paper_execution_engine.restore_state(account, positions, trades)
    if account is None:
        repository.persist_account(session.session_id, await application.state.paper_execution_engine.account())

    async def publish(event: dict[str, object]) -> None:
        await application.state.monitoring_service.record_event(str(event["type"]), event["data"] if isinstance(event.get("data"), dict) else {})
        await application.state.market_service.broadcast(event)
        if event.get("type") == "paper.position_closed" and hasattr(application.state, "validation_engine"):
            await application.state.validation_engine.evaluate("closed_trade")

    application.state.paper_execution_engine._on_event = publish
    application.state.monitoring_service = MonitoringService(session_settings, repository, session, application.state.market_service, application.state.paper_execution_engine, application.state.market_service.broadcast)
    application.state.market_service.set_event_observer(application.state.monitoring_service.record_event)
    application.state.validation_engine = ValidationEngine(session_settings, settings, repository, session, application.state.paper_execution_engine, application.state.monitoring_service, application.state.backtest_engine, application.state.market_service.broadcast)
    if settings.strategy_profile != session.strategy_profile:
        await application.state.monitoring_service.alert("STRATEGY_PROFILE_MISMATCH", AlertSeverity.WARNING, "Configured strategy profile differs from the immutable active paper-session profile")

    async def handle_risk_plan(plan: TradePlan) -> None:
        repository.persist_plan(session.session_id, plan)
        await publish({"type": "risk.plan", "data": plan.model_dump(mode="json")})
        await application.state.paper_execution_engine.process_plan(plan)

    application.state.risk_engine.set_plan_handler(handle_risk_plan)

    async def handle_strategy_signal(signal: SignalSnapshot) -> None:
        repository.persist_signal(session.session_id, signal)
        await publish({"type": "strategy.signal", "data": signal.model_dump(mode="json")})
        await application.state.risk_engine.process_signal(signal)

    application.state.strategy_engine = StrategyEngine(
        session_settings,
        market_status_provider=application.state.market_service.status_snapshot,
        on_signal=handle_strategy_signal,
    )

    async def handle_indicator_snapshot(snapshot: IndicatorSnapshot) -> None:
        # This handler is invoked only after the indicator engine accepts a closed candle.
        await publish({"type": "indicator.snapshot", "data": snapshot.model_dump(mode="json")})
        await application.state.strategy_engine.process_snapshot(snapshot)

    application.state.indicator_engine.set_snapshot_handler(handle_indicator_snapshot)
    if session_settings.indicator_warmup_enabled:
        await application.state.indicator_engine.warm_up(application.state.market_service.adapter.fetch_historical_candles)
    if positions:
        await publish({"type": "paper.recovery", "data": {"status": "recovery_pending"}})
        await application.state.paper_execution_engine.reconcile_recovered_positions(application.state.market_service.adapter.fetch_historical_candles)
    await application.state.market_service.start()
    await application.state.validation_engine.evaluate("startup")

    async def validation_loop() -> None:
        while True:
            await asyncio.sleep(900)
            await application.state.validation_engine.evaluate("periodic")

    application.state.validation_task = asyncio.create_task(validation_loop(), name="forward-validation")
    await application.state.market_service.broadcast({"type": "paper.session", "data": session.model_dump(mode="json")})
    await application.state.market_service.broadcast({"type": "system.health", "data": application.state.monitoring_service.health().model_dump(mode="json")})
    try:
        yield
    finally:
        application.state.validation_task.cancel()
        try:
            await application.state.validation_task
        except asyncio.CancelledError:
            pass
        # Stop accepting market work and dashboard connections before the final
        # durable account sync, so shutdown cannot open a new simulated position.
        await application.state.market_service.stop()
        await application.state.paper_execution_engine.sync_risk_account()


app = FastAPI(title="Scalping Bot", version="0.11.0", lifespan=lifespan)


@app.middleware("http")
async def operational_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or f"req:{datetime.now(UTC).timestamp():.6f}"
    token = request_id_context.set(request_id)
    try:
        content_length = request.headers.get("content-length")
        try:
            declared_size = int(content_length) if content_length else 0
        except ValueError:
            return JSONResponse(status_code=400, content={"error": {"code": "INVALID_CONTENT_LENGTH", "message": "content-length must be an integer", "request_id": request_id}}, headers={"X-Request-ID": request_id})
        if declared_size > get_settings().max_request_body_bytes:
            return JSONResponse(status_code=413, content={"error": {"code": "REQUEST_TOO_LARGE", "message": "request body exceeds the configured limit", "request_id": request_id}})
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; connect-src 'self' ws: wss:; img-src 'self' data:; style-src 'self' 'unsafe-inline'"
        return response
    finally:
        request_id_context.reset(token)


@app.exception_handler(HTTPException)
async def http_error(_: Request, error: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content={"error": {"code": "HTTP_ERROR", "message": str(error.detail), "request_id": request_id_context.get()}})


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
    safe_details = [{"loc": list(item.get("loc", ())), "message": str(item.get("msg", "validation failed")), "type": str(item.get("type", "value_error"))} for item in error.errors()]
    return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "request validation failed", "request_id": request_id_context.get(), "details": safe_details}})


@app.exception_handler(BotError)
async def bot_error(_: Request, error: BotError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": {"code": error.__class__.__name__.upper(), "message": str(error), "request_id": request_id_context.get()}})


@app.exception_handler(Exception)
async def unexpected_error(_: Request, error: Exception) -> JSONResponse:
    logger.exception("Unhandled API error: %s", error)
    return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "internal server error", "request_id": request_id_context.get()}})
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=[],
)
app.include_router(health_router)
app.include_router(status_router)
app.include_router(market_router)
app.include_router(market_ws_router)
app.include_router(indicators_router)
app.include_router(strategy_router)
app.include_router(risk_router)
app.include_router(paper_router)
app.include_router(backtest_router)
app.include_router(optimization_router)
app.include_router(system_router)
app.include_router(validation_router)
