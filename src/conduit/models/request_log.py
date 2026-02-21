from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from conduit.models.base import Base

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conduit.models.api_key import APIKey


class RequestLog(Base):
    __tablename__ = "request_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Identity
    api_key_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
    )
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_deployments.id", ondelete="SET NULL"), nullable=True
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)

    # Metrics
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal("0"), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    cached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Metadata
    request_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    api_key: Mapped[APIKey | None] = relationship(back_populates="request_logs")