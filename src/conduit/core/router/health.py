"""
Circuit breaker for provider deployments.

States:
  CLOSED   -> Healthy, requests flow normally
  OPEN     -> Unhealthy, all requests rejected (cooldown active)
  HALF_OPEN -> Cooldown expired, next request is a probe

Transitions:
  CLOSED -> OPEN:      after `failure_threshold` consecutive failures
  OPEN -> HALF_OPEN:   after `cooldown_seconds` elapse
  HALF_OPEN -> CLOSED: if probe request succeeds
  HALF_OPEN -> OPEN:   if probe request fails (reset cooldown)
"""

from __future__ import annotations

import enum
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.models.deployment import ModelDeployment

logger = structlog.stdlib.get_logger()


class CircuitState(str, enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: int = 60,
        half_open_max_requests: int = 1,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.half_open_max_requests = half_open_max_requests

    def get_state(self, deployment: ModelDeployment) -> CircuitState:
        """Determine the current circuit state from DB fields."""
        now = datetime.now(timezone.utc)

        if deployment.is_healthy:
            return CircuitState.CLOSED

        # Deployment is marked unhealthy — check if cooldown has expired
        if deployment.cooldown_until and deployment.cooldown_until > now:
            return CircuitState.OPEN

        # Cooldown expired → allow a probe
        return CircuitState.HALF_OPEN

    def is_available(self, deployment: ModelDeployment) -> bool:
        """Check if a deployment can accept requests."""
        state = self.get_state(deployment)
        return state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    async def record_success(
        self,
        deployment: ModelDeployment,
        db: AsyncSession,
    ) -> None:
        """Reset failure counters on success."""
        state = self.get_state(deployment)

        if state == CircuitState.HALF_OPEN:
            await logger.ainfo(
                "circuit_breaker.closed",
                deployment=deployment.name,
                previous_failures=deployment.consecutive_failures,
            )

        if deployment.consecutive_failures > 0 or not deployment.is_healthy:
            deployment.consecutive_failures = 0
            deployment.is_healthy = True
            deployment.cooldown_until = None
            await db.flush()

    async def record_failure(
        self,
        deployment: ModelDeployment,
        db: AsyncSession,
    ) -> None:
        """Increment failure counter. Open circuit if threshold reached."""
        deployment.consecutive_failures += 1

        state = self.get_state(deployment)

        if state == CircuitState.HALF_OPEN:
            # Probe failed, then re-open with fresh cooldown
            deployment.is_healthy = False
            deployment.cooldown_until = datetime.now(timezone.utc) + timedelta(
                seconds=self.cooldown_seconds * 2  # Exponential backoff
            )
            await logger.awarning(
                "circuit_breaker.reopened",
                deployment=deployment.name,
                failures=deployment.consecutive_failures,
                cooldown_until=deployment.cooldown_until.isoformat(),
            )

        elif deployment.consecutive_failures >= self.failure_threshold:
            deployment.is_healthy = False
            deployment.cooldown_until = datetime.now(timezone.utc) + timedelta(
                seconds=self.cooldown_seconds
            )
            await logger.awarning(
                "circuit_breaker.opened",
                deployment=deployment.name,
                failures=deployment.consecutive_failures,
                cooldown_until=deployment.cooldown_until.isoformat(),
            )

        await db.flush()