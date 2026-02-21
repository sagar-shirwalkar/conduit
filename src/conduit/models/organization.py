from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from conduit.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from conduit.models.team import Team


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    budget_limit_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    spend_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"), nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    teams: Mapped[list[Team]] = relationship(back_populates="organization", cascade="all, delete-orphan")