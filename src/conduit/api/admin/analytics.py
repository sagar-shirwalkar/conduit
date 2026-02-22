"""Analytics and reporting endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import ORJSONResponse

from conduit.api.deps import AdminKey, DBSession
from conduit.services.analytics_service import AnalyticsService

router = APIRouter()


@router.get("/spend", summary="Spend report")
async def spend_report(
    admin_key: AdminKey,
    db: DBSession,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    group_by: str = Query("model", regex="^(model|provider|key)$"),
) -> ORJSONResponse:
    service = AnalyticsService(db)
    report = await service.get_spend_report(start=start, end=end, group_by=group_by)
    return ORJSONResponse(content=report)


@router.get("/usage", summary="Usage report")
async def usage_report(
    admin_key: AdminKey,
    db: DBSession,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
) -> ORJSONResponse:
    service = AnalyticsService(db)
    report = await service.get_usage_report(start=start, end=end)
    return ORJSONResponse(content=report)