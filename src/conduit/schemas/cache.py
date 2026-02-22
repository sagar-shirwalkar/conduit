"""Cache management schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CacheStatsResponse(BaseModel):
    total_entries: int
    active_entries: int
    expired_entries: int
    total_hits: int
    total_cost_saved_usd: float


class CacheClearRequest(BaseModel):
    model: str | None = Field(None, description="Clear only entries for this model")


class CacheClearResponse(BaseModel):
    exact_cleared: int
    semantic_cleared: int


class CacheConfigUpdate(BaseModel):
    enabled: bool | None = None
    default_ttl_seconds: int | None = Field(None, ge=60, le=604800)
    semantic_threshold: float | None = Field(None, ge=0.5, le=1.0)