"""Read-only forward-paper validation gate endpoints."""

from fastapi import APIRouter, Query, Request


router = APIRouter(tags=["validation"])


@router.get("/api/validation/status")
async def validation_status(request: Request) -> dict[str, object]:
    engine = request.app.state.validation_engine
    if engine.current is None:
        await engine.evaluate("api_initial")
    return engine.current.model_dump(mode="json")


@router.get("/api/validation/rules")
async def validation_rules(request: Request) -> list[dict[str, object]]:
    engine = request.app.state.validation_engine
    if engine.current is None:
        await engine.evaluate("api_initial")
    return [rule.model_dump(mode="json") for rule in engine.current.rule_results]


@router.get("/api/validation/history")
async def validation_history(request: Request, limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0)) -> list[dict[str, object]]:
    engine = request.app.state.validation_engine
    return [item.model_dump(mode="json") for item in engine.store.recent(request.app.state.paper_session.session_id, limit, offset)]
