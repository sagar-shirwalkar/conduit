"""
Semantic cache layer using pgvector.

Performs cosine similarity search over cached prompt embeddings
to find semantically equivalent prompts, even when the wording differs.

Example: "What's the weather in Paris?" ≈ "Tell me Paris weather"
Both should return the cached response if similarity > threshold.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.config import get_settings
from conduit.core.cache.embedding import embed_text, normalize_prompt_for_embedding
from conduit.core.cost.calculator import calculate_cost
from conduit.models.cache_entry import CacheEntry

logger = structlog.stdlib.get_logger()


class SemanticCache:
    """pgvector-backed semantic similarity cache."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._settings = get_settings().cache

    async def lookup(
        self,
        messages: list[dict],
        model: str,
        threshold: float | None = None,
    ) -> CacheEntry | None:
        """
        Search for a semantically similar cached prompt.

        Args:
            messages: Chat messages (OpenAI format)
            model: Model name
            threshold: Cosine similarity threshold (0-1). Default from config.

        Returns:
            CacheEntry if a match is found above threshold, else None.
        """
        threshold = threshold or self._settings.semantic_threshold
        prompt_text = normalize_prompt_for_embedding(messages)

        if not prompt_text.strip():
            return None

        # Generate embedding
        embedding = embed_text(prompt_text, self._settings.embedding_model)

        now = datetime.now(timezone.utc)

        # pgvector cosine distance query
        # cosine_distance = 1 - cosine_similarity
        # So we want distance < (1 - threshold)
        max_distance = 1.0 - threshold

        stmt = (
            select(
                CacheEntry,
                CacheEntry.prompt_embedding.cosine_distance(embedding).label("distance"),
            )
            .where(
                CacheEntry.model == model,
                CacheEntry.expires_at > now,
                CacheEntry.prompt_embedding.cosine_distance(embedding) < max_distance,
            )
            .order_by(text("distance ASC"))
            .limit(1)
        )

        result = await self.db.execute(stmt)
        row = result.first()

        if row is None:
            await logger.adebug("cache.semantic.miss", model=model)
            return None

        entry: CacheEntry = row[0]
        distance: float = row[1]
        similarity = 1.0 - distance

        await logger.ainfo(
            "cache.semantic.hit",
            model=model,
            similarity=f"{similarity:.4f}",
            threshold=threshold,
            entry_id=str(entry.id),
            hit_count=entry.hit_count + 1,
        )

        # Increment hit counter
        entry.hit_count += 1
        cost = calculate_cost(model, entry.prompt_tokens, entry.completion_tokens)
        entry.cost_saved_usd += float(cost)
        await self.db.flush()

        return entry

    async def store(
        self,
        messages: list[dict],
        model: str,
        response_payload: dict[str, Any],
        prompt_tokens: int,
        completion_tokens: int,
        ttl_seconds: int | None = None,
    ) -> CacheEntry:
        """
        Store a new cache entry with embedding.

        Args:
            messages: Original chat messages
            model: Model name
            response_payload: Full response dict to cache
            prompt_tokens: Token count for cost tracking
            completion_tokens: Token count for cost tracking
            ttl_seconds: Override default TTL

        Returns:
            The created CacheEntry
        """
        ttl = ttl_seconds or self._settings.default_ttl_seconds
        prompt_text = normalize_prompt_for_embedding(messages)

        from conduit.core.cache.exact import ExactMatchCache

        prompt_hash = ExactMatchCache.compute_hash(prompt_text, model)
        embedding = embed_text(prompt_text, self._settings.embedding_model)

        entry = CacheEntry(
            prompt_hash=prompt_hash,
            prompt_embedding=embedding,
            model=model,
            prompt_text=prompt_text,
            response_payload=response_payload,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
        )

        self.db.add(entry)
        await self.db.flush()

        await logger.adebug(
            "cache.semantic.stored",
            model=model,
            hash=prompt_hash[:12],
            ttl=ttl,
        )

        return entry

    async def clear(self, model: str | None = None) -> int:
        """Clear cache entries, optionally filtered by model"""
        stmt = delete(CacheEntry)
        if model:
            stmt = stmt.where(CacheEntry.model == model)

        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount  # type: ignore[return-value]

    async def cleanup_expired(self) -> int:
        """Remove expired cache entries"""
        now = datetime.now(timezone.utc)
        stmt = delete(CacheEntry).where(CacheEntry.expires_at < now)
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount  # type: ignore[return-value]

    async def get_stats(self) -> dict[str, Any]:
        """Return cache statistics"""
        now = datetime.now(timezone.utc)

        total_result = await self.db.execute(
            select(func.count(CacheEntry.id))
        )
        total = total_result.scalar_one()

        active_result = await self.db.execute(
            select(func.count(CacheEntry.id)).where(CacheEntry.expires_at > now)
        )
        active = active_result.scalar_one()

        hits_result = await self.db.execute(
            select(func.sum(CacheEntry.hit_count))
        )
        total_hits = hits_result.scalar_one() or 0

        savings_result = await self.db.execute(
            select(func.sum(CacheEntry.cost_saved_usd))
        )
        total_savings = savings_result.scalar_one() or 0.0

        return {
            "total_entries": total,
            "active_entries": active,
            "expired_entries": total - active,
            "total_hits": total_hits,
            "total_cost_saved_usd": round(total_savings, 6),
        }