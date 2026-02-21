from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from conduit.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from conduit.models.api_key import APIKey
    from conduit.models.team import Team


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    TEAM_ADMIN = "team_admin"
    MEMBER = "member"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.MEMBER, nullable=False)
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    team: Mapped[Team | None] = relationship(back_populates="members")
    api_keys: Mapped[list[APIKey]] = relationship(back_populates="user", cascade="all, delete-orphan")