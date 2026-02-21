"""V1 API router for OpenAI-compatible endpoints."""

from fastapi import APIRouter

from conduit.api.v1.chat import router as chat_router
from conduit.api.v1.models import router as models_router

v1_router = APIRouter(prefix="/v1", tags=["OpenAI-Compatible"])

v1_router.include_router(chat_router)
v1_router.include_router(models_router)