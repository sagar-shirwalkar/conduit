"""Model deployment management schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateDeploymentRequest(BaseModel):
    name: str = Field(..., max_length=255)
    provider: str
    model_name: str = Field(..., max_length=255)
    api_base: str = Field(..., max_length=512)
    api_key: str = Field(..., description="Provider API key (will be encrypted)")
    priority: int = Field(1, ge=1, le=100)
    weight: int = Field(100, ge=1, le=1000)
    max_rpm: int | None = Field(None, ge=1)
    max_tpm: int | None = Field(None, ge=1)


class DeploymentInfo(BaseModel):
    id: uuid.UUID
    name: str
    provider: str
    model_name: str
    api_base: str
    priority: int
    weight: int
    is_active: bool
    is_healthy: bool
    cooldown_until: datetime | None
    consecutive_failures: int
    max_rpm: int | None
    max_tpm: int | None
    created_at: datetime


class UpdateDeploymentRequest(BaseModel):
    priority: int | None = Field(None, ge=1, le=100)
    weight: int | None = Field(None, ge=1, le=1000)
    api_key: str | None = None
    is_active: bool | None = None
    max_rpm: int | None = Field(None, ge=1)
    max_tpm: int | None = Field(None, ge=1)


class DeploymentListResponse(BaseModel):
    deployments: list[DeploymentInfo]
    total: int