"""
Unified cache manager.

Two-tier lookup:
  1. Exact match (Redis) — O(1), nanosecond latency
  2. Semantic match (pgvector) — cosine similarity search

On cache miss after provider response, both layers are populated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.config import get_settings
from conduit.core.cache.embedding import normalize_prompt_for_embedding
from conduit.core.cache.exact import ExactMatchCache
from conduit.core.cache.semantic import SemanticCache
from conduit.schemas.completion import ChatCompletionResponse

logger = structlog.stdlib.get_logger()


@dataclass
class CacheResult:
    """Result of a cache lookup."""

    hit: bool
    response: ChatCompletionResponse | None = None
    response_payload: dict[str, Any] | None = None
    source: str = "none"  # "exact" | "semantic" | "none"
    similarity: float = 0.0


class CacheManager:
    """
    Unified two-tier cache: exact (Redis) -> semantic (pgvector).

    Usage:
        manager = CacheManager(db)
        result = await manager.lookup(messages, model)
        if result.hit:
            return result.response_payload
        await manager.store(messages, model, response_payload, ...)
    """

    def __init__(self, db: AsyncSession) -> None:
        self._settings = get_settings().cache
        self._exact = ExactMatchCache()
        self._semantic = SemanticCache(db)
        self._db = db

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    async def lookup(
        self,
        messages: list[dict[str, Any]],
        model: str,
    ) -> CacheResult:
        """
        Look up a prompt in the cache.

        Tier 1: Exact hash match (Redis, 1ms)
        Tier 2: Semantic similarity (pgvector, 5-20ms)
        """
        if not self.enabled:
            return CacheResult(hit=False)

        prompt_text = normalize_prompt_for_embedding(messages)
        if not prompt_text.strip():
            return CacheResult(hit=False)

        prompt_hash = ExactMatchCache.compute_hash(prompt_text, model)

        # Tier 1: Exact Match (Redis)
        exact_payload = await self._exact.get(prompt_hash)
        if exact_payload is not None:
            await logger.ainfo("cache.hit", source="exact", model=model)
            return CacheResult(
                hit=True,
                response_payload=exact_payload,
                source="exact",
                similarity=1.0,
            )

        # Tier 2: Semantic Match (pgvector)
        try:
            entry = await self._semantic.lookup(messages, model)
            if entry is not None:
                # Promote to exact cache for faster future hits
                await self._exact.set(prompt_hash, entry.response_payload)

                await logger.ainfo("cache.hit", source="semantic", model=model)
                return CacheResult(
                    hit=True,
                    response_payload=entry.response_payload,
                    source="semantic",
                )
        except Exception as e:
            await logger.awarning("cache.semantic.error", error=str(e))

        return CacheResult(hit=False)

    async def store(
        self,
        messages: list[dict[str, Any]],
        model: str,
        response_payload: dict[str, Any],
        prompt_tokens: int,
        completion_tokens: int,
        ttl_seconds: int | None = None,
    ) -> None:
        """
        Store a response in both cache tiers.

        Called after a successful (non-cached) provider response.
        """
        if not self.enabled:
            return

        prompt_text = normalize_prompt_for_embedding(messages)
        if not prompt_text.strip():
            return

        prompt_hash = ExactMatchCache.compute_hash(prompt_text, model)

        try:
            # Store in Redis (exact match)
            await self._exact.set(
                prompt_hash,
                response_payload,
                ttl_seconds=ttl_seconds or self._settings.exact_match_ttl_seconds,
            )

            # Store in pgvector (semantic match)
            await self._semantic.store(
                messages=messages,
                model=model,
                response_payload=response_payload,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                ttl_seconds=ttl_seconds,
            )

        except Exception as e:
            # Cache write failure should never break the request
            await logger.awarning("cache.store.error", error=str(e))

    async def clear(self, model: str | None = None) -> dict[str, int]:
        """Clear both cache tiers."""
        exact_cleared = await self._exact.clear(model)
        semantic_cleared = await self._semantic.clear(model)
        return {"exact_cleared": exact_cleared, "semantic_cleared": semantic_cleared}

    async def get_stats(self) -> dict[str, Any]:
        """Return combined cache statistics."""
        return await self._semantic.get_stats()