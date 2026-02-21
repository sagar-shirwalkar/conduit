from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from conduit.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProviderType(str, enum.Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    MISTRAL = "mistral"
    COHERE = "cohere"
    BEDROCK = "bedrock"
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"


class ModelDeployment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "model_deployments"

    # Identity
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    provider: Mapped[ProviderType] = mapped_column(Enum(ProviderType), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Connection
    api_base: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(String(1024), nullable=False)

    # Routing
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Health
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Rate limits
    max_rpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_tpm: Mapped[int | None] = mapped_column(Integer, nullable=True)