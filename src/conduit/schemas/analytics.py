"""Analytics and reporting schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class SpendQuery(BaseModel):
    start: datetime | None = None
    end: datetime | None = None
    group_by: str = "model"  # model | provider | key | team


class SpendReportResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    total_cost_usd: float
    total_requests: int
    total_tokens: int
    breakdown: list[dict[str, Any]]
    cache_hits: int
    cache_savings_usd: float


class UsageReportResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    total_requests: int
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    error_count: int
    error_rate: float
    by_model: dict[str, int]
    by_provider: dict[str, int]