from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from conduit.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from conduit.models.request_log import RequestLog
    from conduit.models.user import User


class APIKey(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "api_keys"

    # Key data (raw key is never stored)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    alias: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Ownership
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )

    # Access control
    allowed_models: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    budget_limit_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    spend_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"), nullable=False)
    rate_limit_rpm: Mapped[int | None] = mapped_column(nullable=True)
    rate_limit_tpm: Mapped[int | None] = mapped_column(nullable=True)

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped[User] = relationship(back_populates="api_keys")
    request_logs: Mapped[list[RequestLog]] = relationship(back_populates="api_key")