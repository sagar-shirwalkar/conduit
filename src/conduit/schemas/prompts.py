"""Prompt template management schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreatePromptRequest(BaseModel):
    name: str = Field(..., max_length=255)
    template: str
    description: str | None = Field(None, max_length=1024)
    variables: dict[str, Any] | None = None
    model_hint: str | None = None


class PromptInfo(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    description: str | None
    template: str
    variables: dict[str, Any]
    model_hint: str | None
    is_active: bool
    created_at: datetime


class RenderPromptRequest(BaseModel):
    variables: dict[str, Any]


class RenderPromptResponse(BaseModel):
    rendered: str
    template_name: str
    template_version: int


class PromptListResponse(BaseModel):
    templates: list[PromptInfo]
    total: int