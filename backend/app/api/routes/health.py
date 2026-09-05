from fastapi import APIRouter

router = APIRouter(tags=["foundation"])


@router.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
