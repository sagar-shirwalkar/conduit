"""Cache management endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import ORJSONResponse

from conduit.api.deps import AdminKey, DBSession
from conduit.core.cache.manager import CacheManager
from conduit.schemas.cache import CacheClearRequest, CacheClearResponse, CacheStatsResponse

router = APIRouter()


@router.get("/stats", response_model=CacheStatsResponse, summary="Cache statistics")
async def cache_stats(admin_key: AdminKey, db: DBSession) -> CacheStatsResponse:
    manager = CacheManager(db)
    stats = await manager.get_stats()
    return CacheStatsResponse(**stats)


@router.post("/clear", response_model=CacheClearResponse, summary="Clear cache")
async def clear_cache(
    body: CacheClearRequest, admin_key: AdminKey, db: DBSession
) -> CacheClearResponse:
    manager = CacheManager(db)
    result = await manager.clear(model=body.model)
    return CacheClearResponse(**result)