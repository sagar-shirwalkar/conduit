"""
Sliding window rate limiter backed by Redis.

Supports:
  - RPM (requests per minute) — checked pre-request
  - TPM (tokens per minute)  — checked pre-request (estimated), updated post-request

Returns rate limit headers for RFC 6585 compliance:
  X-RateLimit-Limit-Requests
  X-RateLimit-Remaining-Requests
  X-RateLimit-Reset-Requests
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import redis.asyncio as aioredis
import structlog

from conduit.common.errors import RateLimitError
from conduit.config import get_settings

logger = structlog.stdlib.get_logger()


@dataclass
class RateLimitResult:
    """Result of a rate limit check, including header values."""

    allowed: bool
    limit: int
    remaining: int
    reset_seconds: float

    def to_headers(self, kind: str = "requests") -> dict[str, str]:
        return {
            f"x-ratelimit-limit-{kind}": str(self.limit),
            f"x-ratelimit-remaining-{kind}": str(max(0, self.remaining)),
            f"x-ratelimit-reset-{kind}": f"{self.reset_seconds:.1f}",
        }


# Lua: sliding window counter that returns (is_rejected, current_count, ttl_remaining)
RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local increment = tonumber(ARGV[4])

-- Remove expired entries
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- Count current usage
local current = redis.call('ZCARD', key)

if current + increment <= limit then
    -- Add entries for this request
    for i = 1, increment do
        redis.call('ZADD', key, now, now .. '-' .. math.random(1000000) .. '-' .. i)
    end
    redis.call('EXPIRE', key, window + 1)
    return {0, current + increment, window}
else
    -- Get the oldest entry to calculate reset time
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local reset = 0
    if #oldest > 0 then
        reset = tonumber(oldest[2]) + window - now
    end
    return {1, current, reset}
end
"""


class RateLimiter:
    """Async rate limiter using Redis sorted sets (sliding window)."""

    def __init__(self, redis_url: str | None = None) -> None:
        settings = get_settings()
        self._redis: aioredis.Redis = aioredis.from_url(
            redis_url or settings.redis.url,
            decode_responses=True,
        )
        self._prefix = settings.redis.key_prefix
        self._script_sha: str | None = None

    async def _ensure_script(self) -> str:
        if self._script_sha is None:
            self._script_sha = await self._redis.script_load(RATE_LIMIT_SCRIPT)
        return self._script_sha

    async def check(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
        increment: int = 1,
    ) -> RateLimitResult:
        """
        Check and consume rate limit quota.

        Args:
            identifier: Rate limit bucket key (e.g., "rpm:key:{key_id}")
            limit: Maximum allowed in window
            window_seconds: Sliding window duration
            increment: Units to consume (1 for RPM, token_count for TPM)

        Returns:
            RateLimitResult with headers and allowed/rejected status
        """
        key = f"{self._prefix}ratelimit:{identifier}"
        now = time.time()

        try:
            sha = await self._ensure_script()
            result = await self._redis.evalsha(
                sha, 1, key, str(limit), str(window_seconds), str(now), str(increment)
            )
            rejected, current, reset = int(result[0]), int(result[1]), float(result[2])

        except aioredis.ConnectionError:
            await logger.awarning("rate_limiter.redis_unavailable", identifier=identifier)
            # Fail-open: allow request if Redis is down
            return RateLimitResult(
                allowed=True, limit=limit, remaining=limit, reset_seconds=0
            )
        except aioredis.ResponseError:
            # Script may have been flushed — reload and retry once
            self._script_sha = None
            sha = await self._ensure_script()
            result = await self._redis.evalsha(
                sha, 1, key, str(limit), str(window_seconds), str(now), str(increment)
            )
            rejected, current, reset = int(result[0]), int(result[1]), float(result[2])

        return RateLimitResult(
            allowed=not rejected,
            limit=limit,
            remaining=limit - current,
            reset_seconds=max(0, reset),
        )

    async def check_or_raise(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
        increment: int = 1,
    ) -> RateLimitResult:
        """Check rate limit — raises RateLimitError if exceeded."""
        result = await self.check(identifier, limit, window_seconds, increment)
        if not result.allowed:
            raise RateLimitError(
                f"Rate limit exceeded: {limit} per {window_seconds}s",
                details={
                    "limit": limit,
                    "window_seconds": window_seconds,
                    "retry_after": result.reset_seconds,
                },
            )
        return result

    async def update_token_usage(
        self,
        identifier: str,
        token_count: int,
        limit: int,
        window_seconds: int = 60,
    ) -> RateLimitResult:
        """
        Post-request: record actual token usage for TPM tracking.

        This does not reject — it just updates the counter.
        Rejection happens on the next pre-request check.
        """
        return await self.check(
            identifier=identifier,
            limit=limit,
            window_seconds=window_seconds,
            increment=token_count,
        )

    async def close(self) -> None:
        await self._redis.aclose()


# Singleton

_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the singleton rate limiter."""
    global _rate_limiter  # noqa: PLW0603
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter