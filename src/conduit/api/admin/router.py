"""Admin API router for management endpoints."""

from fastapi import APIRouter


from conduit.api.admin.analytics import router as analytics_router
from conduit.api.admin.cache import router as cache_router
from conduit.api.admin.deployments import router as deployments_router
from conduit.api.admin.guardrails import router as guardrails_router
from conduit.api.admin.health import router as health_router
from conduit.api.admin.keys import router as keys_router
from conduit.api.admin.prompts import router as prompts_router

admin_router = APIRouter(prefix="/admin/v1", tags=["Admin"])

admin_router.include_router(health_router, prefix="/health")
admin_router.include_router(keys_router, prefix="/keys")
admin_router.include_router(deployments_router, prefix="/models/deployments")

admin_router = APIRouter(prefix="/admin/v1", tags=["Admin"])

admin_router.include_router(health_router, prefix="/health")
admin_router.include_router(keys_router, prefix="/keys")
admin_router.include_router(deployments_router, prefix="/models/deployments")
admin_router.include_router(guardrails_router, prefix="/guardrails")
admin_router.include_router(prompts_router, prefix="/prompts")
admin_router.include_router(cache_router, prefix="/cache")
admin_router.include_router(analytics_router, prefix="/analytics")