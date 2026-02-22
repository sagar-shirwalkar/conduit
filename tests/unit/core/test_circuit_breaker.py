"""Tests for circuit breaker state machine."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from conduit.core.router.health import CircuitBreaker, CircuitState
from conduit.models.deployment import ModelDeployment, ProviderType


def _make_deployment(**overrides) -> ModelDeployment:
    d = ModelDeployment.__new__(ModelDeployment)
    d.id = uuid.uuid4()
    d.name = "test-deploy"
    d.provider = ProviderType.OPENAI
    d.model_name = "gpt-5"
    d.api_base = "https://api.openai.com/v1"
    d.api_key_encrypted = "enc_key"
    d.priority = 1
    d.weight = 100
    d.is_active = True
    d.is_healthy = True
    d.cooldown_until = None
    d.consecutive_failures = 0
    d.max_rpm = None
    d.max_tpm = None
    for k, v in overrides.items():
        setattr(d, k, v)
    return d


@pytest.mark.unit
class TestCircuitBreaker:
    def test_healthy_deployment_is_closed(self) -> None:
        cb = CircuitBreaker()
        d = _make_deployment()
        assert cb.get_state(d) == CircuitState.CLOSED
        assert cb.is_available(d)

    def test_unhealthy_with_cooldown_is_open(self) -> None:
        cb = CircuitBreaker()
        d = _make_deployment(
            is_healthy=False,
            cooldown_until=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        assert cb.get_state(d) == CircuitState.OPEN
        assert not cb.is_available(d)

    def test_unhealthy_with_expired_cooldown_is_half_open(self) -> None:
        cb = CircuitBreaker()
        d = _make_deployment(
            is_healthy=False,
            cooldown_until=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        assert cb.get_state(d) == CircuitState.HALF_OPEN
        assert cb.is_available(d)

    async def test_record_failure_opens_circuit_at_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)
        d = _make_deployment()
        db = AsyncMock()

        # 2 failures — stays closed
        await cb.record_failure(d, db)
        assert d.consecutive_failures == 1
        assert d.is_healthy is True

        await cb.record_failure(d, db)
        assert d.consecutive_failures == 2
        assert d.is_healthy is True

        # 3rd failure — opens
        await cb.record_failure(d, db)
        assert d.consecutive_failures == 3
        assert d.is_healthy is False
        assert d.cooldown_until is not None

    async def test_record_success_resets_counters(self) -> None:
        cb = CircuitBreaker()
        d = _make_deployment(
            is_healthy=False,
            consecutive_failures=5,
            cooldown_until=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        db = AsyncMock()

        await cb.record_success(d, db)
        assert d.consecutive_failures == 0
        assert d.is_healthy is True
        assert d.cooldown_until is None

    async def test_half_open_failure_reopens_with_longer_cooldown(self) -> None:
        cb = CircuitBreaker(cooldown_seconds=30)
        d = _make_deployment(
            is_healthy=False,
            consecutive_failures=3,
            cooldown_until=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        db = AsyncMock()

        assert cb.get_state(d) == CircuitState.HALF_OPEN

        await cb.record_failure(d, db)
        assert d.is_healthy is False
        assert d.cooldown_until is not None
        # Exponential backoff: 30 * 2 = 60 seconds
        expected_min = datetime.now(timezone.utc) + timedelta(seconds=55)
        assert d.cooldown_until > expected_min