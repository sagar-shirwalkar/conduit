"""Semantic cache entry — stores prompt embeddings and cached responses."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.models.base import Base


class CacheEntry(Base):
    __tablename__ = "cache_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Lookup Keys
    prompt_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # SHA-256 for exact-match fast path
    prompt_embedding: Mapped[list[float]] = mapped_column(
        Vector(384), nullable=False
    )  # pgvector for semantic similarity
    model: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Cached Data
    prompt_text: Mapped[str] = mapped_column(String, nullable=False)
    response_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)

    # Metrics
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_saved_usd: Mapped[float] = mapped_column(default=0.0, nullable=False)

    # Lifecycle
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_cache_semantic",
            prompt_embedding,
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"prompt_embedding": "vector_cosine_ops"},
        ),
        Index("ix_cache_model_hash", model, prompt_hash),
    )