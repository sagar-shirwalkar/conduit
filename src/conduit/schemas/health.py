"""Health check schemas."""

from __future__ import annotations

from pydantic import BaseModel


class LivenessResponse(BaseModel):
    status: str = "ok"
    version: str


class ReadinessResponse(BaseModel):
    status: str
    database: str  # "connected" | "disconnected"
    redis: str     # "connected" | "disconnected"


class ProviderHealth(BaseModel):
    name: str
    provider: str
    model_name: str
    is_healthy: bool
    consecutive_failures: int
    cooldown_until: str | None


class ProvidersHealthResponse(BaseModel):
    providers: list[ProviderHealth]