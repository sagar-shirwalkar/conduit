"""Guardrail rule definitions stored in DB for dynamic management."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from conduit.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class GuardrailType(str, enum.Enum):
    PII = "pii"
    INJECTION = "injection"
    CONTENT_FILTER = "content_filter"
    REGEX = "regex"
    WORD_LIST = "word_list"
    MAX_TOKENS = "max_tokens"


class GuardrailStage(str, enum.Enum):
    PRE = "pre"
    POST = "post"
    BOTH = "both"


class GuardrailAction(str, enum.Enum):
    BLOCK = "block"
    REDACT = "redact"
    WARN = "warn"
    LOG = "log"


class GuardrailRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "guardrail_rules"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    type: Mapped[GuardrailType] = mapped_column(Enum(GuardrailType), nullable=False)
    stage: Mapped[GuardrailStage] = mapped_column(Enum(GuardrailStage), nullable=False)
    action: Mapped[GuardrailAction] = mapped_column(Enum(GuardrailAction), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)