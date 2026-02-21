from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from conduit.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from conduit.models.organization import Organization
    from conduit.models.user import User


class Team(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    budget_limit_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    spend_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"), nullable=False)
    allowed_models: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    rate_limit_rpm: Mapped[int | None] = mapped_column(nullable=True)
    rate_limit_tpm: Mapped[int | None] = mapped_column(nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship(back_populates="teams")
    members: Mapped[list[User]] = relationship(back_populates="team", cascade="all, delete-orphan")