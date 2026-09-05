"""Backend-owned WebSocket for dashboard market events."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.market.service import MarketDataService

router = APIRouter()


@router.websocket("/ws/market")
async def market_websocket(websocket: WebSocket) -> None:
    service: MarketDataService = websocket.app.state.market_service
    await service.connect_dashboard(websocket)
    session = websocket.app.state.paper_session
    await websocket.send_json({"type": "paper.session", "data": session.model_dump(mode="json")})
    await websocket.send_json({"type": "paper.metrics", "data": websocket.app.state.paper_repository.metrics(session).model_dump(mode="json")})
    await websocket.send_json({"type": "system.health", "data": websocket.app.state.monitoring_service.health().model_dump(mode="json")})
    await websocket.send_json({"type": "paper.recovery", "data": {"status": websocket.app.state.paper_execution_engine.recovery_status.value}})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await service.disconnect_dashboard(websocket)
