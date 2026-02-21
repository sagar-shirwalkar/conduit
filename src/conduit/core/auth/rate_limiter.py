"""Token bucket rate limiter backed by Redis."""

from __future__ import annotations

import time

import redis.asyncio as aioredis
import structlog

from conduit.common.errors import RateLimitError
from conduit.config import get_settings

logger = structlog.stdlib.get_logger()

# Lua script for atomic rate limiting (sliding window counter)
RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

-- Remove expired entries
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- Count current entries
local count = redis.call('ZCARD', key)

if count < limit then
    -- Add this request
    redis.call('ZADD', key, now, now .. '-' .. math.random(1000000))
    redis.call('EXPIRE', key, window)
    return 0  -- allowed
else
    return 1  -- rejected
end
"""


class RateLimiter:
    def __init__(self) -> None:
        settings = get_settings()
        self._redis: aioredis.Redis = aioredis.from_url(
            settings.redis.url,
            decode_responses=True,
        )
        self._prefix = settings.redis.key_prefix
        self._script_sha: str | None = None

    async def _ensure_script(self) -> str:
        if self._script_sha is None:
            self._script_sha = await self._redis.script_load(RATE_LIMIT_SCRIPT)
        return self._script_sha

    async def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> None:
        """
        Check if a request is within rate limits.

        Args:
            identifier: Unique key (e.g., "rpm:key:{key_id}")
            limit: Maximum requests allowed in the window
            window_seconds: Sliding window size

        Raises:
            RateLimitError: If rate limit is exceeded
        """
        key = f"{self._prefix}ratelimit:{identifier}"
        now = time.time()

        try:
            sha = await self._ensure_script()
            rejected = await self._redis.evalsha(
                sha, 1, key, str(limit), str(window_seconds), str(now)
            )
        except aioredis.ConnectionError:
            # If Redis is down, allow the request (fail-open)
            await logger.awarning("rate_limiter.redis_unavailable", identifier=identifier)
            return

        if rejected:
            raise RateLimitError(
                f"Rate limit exceeded: {limit} requests per {window_seconds}s",
                details={"limit": limit, "window_seconds": window_seconds},
            )

    async def close(self) -> None:
        await self._redis.aclose()