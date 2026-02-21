"""API key management schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class CreateAPIKeyRequest(BaseModel):
    alias: str | None = Field(None, max_length=255)
    user_email: str = Field(..., description="Email of the user to assign the key to")
    team_id: uuid.UUID | None = None
    allowed_models: list[str] | None = None
    budget_limit_usd: Decimal | None = Field(None, ge=0)
    rate_limit_rpm: int | None = Field(None, ge=1)
    rate_limit_tpm: int | None = Field(None, ge=1)
    expires_in_days: int | None = Field(None, ge=1)


class CreateAPIKeyResponse(BaseModel):
    """Returned ONCE — the raw key is never retrievable again."""

    key: str
    key_prefix: str
    id: uuid.UUID
    alias: str | None
    created_at: datetime


class APIKeyInfo(BaseModel):
    id: uuid.UUID
    key_prefix: str
    alias: str | None
    user_id: uuid.UUID
    team_id: uuid.UUID | None
    allowed_models: list[str] | None
    budget_limit_usd: Decimal | None
    spend_usd: Decimal
    rate_limit_rpm: int | None
    rate_limit_tpm: int | None
    is_active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class UpdateAPIKeyRequest(BaseModel):
    alias: str | None = None
    allowed_models: list[str] | None = None
    budget_limit_usd: Decimal | None = Field(None, ge=0)
    rate_limit_rpm: int | None = Field(None, ge=1)
    rate_limit_tpm: int | None = Field(None, ge=1)
    is_active: bool | None = None


class APIKeyListResponse(BaseModel):
    keys: list[APIKeyInfo]
    total: int