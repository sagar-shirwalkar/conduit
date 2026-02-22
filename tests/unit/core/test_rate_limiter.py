"""Tests for rate limiter (requires Redis)."""

from __future__ import annotations

import pytest

from conduit.core.auth.rate_limiter import RateLimiter


@pytest.mark.unit
class TestRateLimitResult:
    def test_headers_format(self) -> None:
        from conduit.core.auth.rate_limiter import RateLimitResult

        result = RateLimitResult(allowed=True, limit=60, remaining=58, reset_seconds=45.5)
        headers = result.to_headers("requests")

        assert headers["x-ratelimit-limit-requests"] == "60"
        assert headers["x-ratelimit-remaining-requests"] == "58"
        assert headers["x-ratelimit-reset-requests"] == "45.5"

    def test_negative_remaining_clamped_to_zero(self) -> None:
        from conduit.core.auth.rate_limiter import RateLimitResult

        result = RateLimitResult(allowed=False, limit=10, remaining=-5, reset_seconds=10.0)
        headers = result.to_headers("requests")
        assert headers["x-ratelimit-remaining-requests"] == "0"