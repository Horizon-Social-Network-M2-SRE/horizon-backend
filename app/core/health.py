import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.db import ping_mongo
from app.core.redis import ping_redis

router = APIRouter(tags=["health"])

CHECK_TIMEOUT_SECONDS = 2.0


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: the process is up. Does not touch MongoDB or Redis."""
    return {"status": "ok"}


async def _check(coro) -> str:
    try:
        await asyncio.wait_for(coro, CHECK_TIMEOUT_SECONDS)
    except Exception:
        return "down"
    return "ok"


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    """Readiness: MongoDB and Redis answer a ping. 503 if either is down."""
    state = request.app.state
    mongo, redis = await asyncio.gather(_check(ping_mongo(state.db)), _check(ping_redis(state.redis)))
    checks = {"mongodb": mongo, "redis": redis}
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        {"status": "ok" if ok else "unavailable", "checks": checks},
        status_code=200 if ok else 503,
    )
