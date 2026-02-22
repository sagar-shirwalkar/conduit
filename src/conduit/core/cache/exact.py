"""
Exact-match cache layer using Redis.

Provides a fast O(1) lookup before the slower semantic search.
Key: SHA-256(normalized_prompt + model)
Value: Serialized response payload (JSON)
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import redis.asyncio as aioredis
import structlog

from conduit.config import get_settings

logger = structlog.stdlib.get_logger()


class ExactMatchCache:
    """Redis-backed exact match cache for identical prompts"""

    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        settings = get_settings()
        if redis_client:
            self._redis = redis_client
        else:
            self._redis = aioredis.from_url(
                settings.redis.url, decode_responses=True
            )
        self._prefix = f"{settings.redis.key_prefix}cache:exact:"
        self._default_ttl = settings.cache.exact_match_ttl_seconds

    @staticmethod
    def compute_hash(prompt_text: str, model: str) -> str:
        """Compute SHA-256 hash of prompt + model for exact matching."""
        raw = f"{model}::{prompt_text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def get(self, prompt_hash: str) -> dict[str, Any] | None:
        """
        Look up an exact-match cache entry.

        Returns deserialized response payload or None.
        """
        key = f"{self._prefix}{prompt_hash}"
        try:
            data = await self._redis.get(key)
            if data is None:
                return None

            await logger.adebug("cache.exact.hit", hash=prompt_hash[:12])
            return json.loads(data)

        except aioredis.ConnectionError:
            await logger.awarning("cache.exact.redis_unavailable")
            return None

    async def set(
        self,
        prompt_hash: str,
        payload: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """Store a response in the exact-match cache"""
        key = f"{self._prefix}{prompt_hash}"
        ttl = ttl_seconds or self._default_ttl
        try:
            await self._redis.setex(key, ttl, json.dumps(payload))
            await logger.adebug("cache.exact.stored", hash=prompt_hash[:12], ttl=ttl)
        except aioredis.ConnectionError:
            await logger.awarning("cache.exact.redis_unavailable")

    async def delete(self, prompt_hash: str) -> None:
        """Remove an entry from exact-match cache."""
        key = f"{self._prefix}{prompt_hash}"
        try:
            await self._redis.delete(key)
        except aioredis.ConnectionError:
            pass

    async def clear(self, model: str | None = None) -> int:
        """Clear exact-match cache entries. Returns count deleted"""
        try:
            pattern = f"{self._prefix}*"
            count = 0
            async for key in self._redis.scan_iter(match=pattern, count=100):
                await self._redis.delete(key)
                count += 1
            return count
        except aioredis.ConnectionError:
            return 0

    async def close(self) -> None:
        await self._redis.aclose()