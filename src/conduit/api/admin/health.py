"""Health check endpoints for liveness/readiness probes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import ORJSONResponse
from sqlalchemy import text

from conduit import __version__
from conduit.api.deps import DBSession
from conduit.schemas.health import LivenessResponse, ReadinessResponse

router = APIRouter()


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
)
async def liveness() -> LivenessResponse:
    return LivenessResponse(version=__version__)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
)
async def readiness(db: DBSession) -> ORJSONResponse:
    db_status = "disconnected"
    redis_status = "disconnected"

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        pass

    # Check Redis
    try:
        import redis.asyncio as aioredis
        from conduit.config import get_settings

        settings = get_settings()
        r = aioredis.from_url(settings.redis.url)
        await r.ping()
        redis_status = "connected"
        await r.aclose()
    except Exception:
        pass

    overall = "ok" if db_status == "connected" else "degraded"

    return ORJSONResponse(
        status_code=200 if overall == "ok" else 503,
        content=ReadinessResponse(
            status=overall,
            database=db_status,
            redis=redis_status,
        ).model_dump(),
    )