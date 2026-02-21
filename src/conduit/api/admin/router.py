"""Admin API router for management endpoints."""

from fastapi import APIRouter

from conduit.api.admin.deployments import router as deployments_router
from conduit.api.admin.health import router as health_router
from conduit.api.admin.keys import router as keys_router

admin_router = APIRouter(prefix="/admin/v1", tags=["Admin"])

admin_router.include_router(health_router, prefix="/health")
admin_router.include_router(keys_router, prefix="/keys")
admin_router.include_router(deployments_router, prefix="/models/deployments")