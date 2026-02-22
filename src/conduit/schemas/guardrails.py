"""Guardrail rule management schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateGuardrailRuleRequest(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = Field(None, max_length=1024)
    type: str  # pii | injection | content_filter | regex | word_list | max_tokens
    stage: str  # pre | post | both
    action: str  # block | redact | warn | log
    config: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(100, ge=1, le=10000)


class GuardrailRuleInfo(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    type: str
    stage: str
    action: str
    config: dict[str, Any]
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UpdateGuardrailRuleRequest(BaseModel):
    description: str | None = None
    action: str | None = None
    config: dict[str, Any] | None = None
    priority: int | None = Field(None, ge=1, le=10000)
    is_active: bool | None = None


class GuardrailRuleListResponse(BaseModel):
    rules: list[GuardrailRuleInfo]
    total: int


class GuardrailTestRequest(BaseModel):
    """Test guardrails against sample input without making an LLM call."""

    messages: list[dict[str, Any]]
    model: str = "gpt-4o"


class GuardrailTestResponse(BaseModel):
    passed: bool
    violations: list[dict[str, Any]]
    pii_found: list[str]
    injection_score: float
    content_filter_categories: list[str]
    modified_messages: list[dict[str, Any]] | None