from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.models.base import Base


class AuditEvent(Base):
    """Append-only audit log. No UPDATE or DELETE operations should ever be performed."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False)  # "user" | "api_key" | "system"
    action: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # "key.created", "deployment.updated"
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )