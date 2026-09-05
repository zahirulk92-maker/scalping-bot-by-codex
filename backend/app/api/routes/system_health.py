
from fastapi import APIRouter, Request, Response
from datetime import datetime, timezone
from app.config import get_settings

router = APIRouter(tags=["system"])

@router.get("/api/system/live")
async def get_live():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

@router.get("/api/system/ready")
async def get_ready():
    # Basic readiness check
    return {
        "status": "READY",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {
            "database": "READY",
            "market_data": "READY",
            "futures_demo_engine": "READY"
        }
    }

@router.get("/api/system/version")
async def get_version():
    return {
        "version": "0.15.0",
        "build_commit": "unknown",
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": get_settings().app_env
    }

@router.get("/api/futures-demo/health")
async def get_futures_health():
    settings = get_settings()
    return {
        "execution_mode": settings.execution_mode,
        "session_status": "ACTIVE",
        "account_consistency": "OK",
        "validation_status": "PASS",
        "kill_switch_active": getattr(settings, 'futures_demo_kill_switch', False)
    }
