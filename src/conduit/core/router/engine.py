"""
Router engine — selects the best deployment for a request.

Phase 1: Simple priority-based routing with fallback.
Phase 2 will add: latency-based, cost-based, weighted round-robin.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.common.errors import NoHealthyDeploymentError
from conduit.models.deployment import ModelDeployment

logger = structlog.stdlib.get_logger()


class RouterEngine:
    """Selects the optimal deployment for a given model request."""

    async def route(
        self,
        model: str,
        db: AsyncSession,
    ) -> ModelDeployment:
        """
        Find the best healthy deployment for the requested model.

        Strategy (Phase 1 — priority):
          1. Find all active deployments matching the model
          2. Filter out unhealthy / cooled-down deployments
          3. Return highest-priority (lowest number) deployment

        Raises:
            NoHealthyDeploymentError: If no deployment is available
        """
        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(ModelDeployment)
            .where(
                ModelDeployment.model_name == model,
                ModelDeployment.is_active.is_(True),
            )
            .order_by(ModelDeployment.priority.asc())
        )
        deployments = list(result.scalars().all())

        if not deployments:
            raise NoHealthyDeploymentError(
                f"No deployments configured for model '{model}'. "
                f"Register one via POST /admin/v1/models/deployments"
            )

        # Filter healthy deployments
        healthy = [
            d
            for d in deployments
            if d.is_healthy and (d.cooldown_until is None or d.cooldown_until < now)
        ]

        if not healthy:
            raise NoHealthyDeploymentError(
                f"All deployments for model '{model}' are currently unhealthy. "
                f"Total deployments: {len(deployments)}"
            )

        chosen = healthy[0]

        await logger.ainfo(
            "router.selected",
            model=model,
            deployment=chosen.name,
            provider=chosen.provider.value,
            priority=chosen.priority,
            candidates=len(healthy),
        )

        return chosen

    async def mark_failure(
        self,
        deployment: ModelDeployment,
        db: AsyncSession,
    ) -> None:
        """Mark a deployment as having failed (for circuit breaking)."""
        deployment.consecutive_failures += 1

        # Simple circuit breaker: cool down after 3 consecutive failures
        if deployment.consecutive_failures >= 3:
            from datetime import timedelta

            deployment.is_healthy = False
            deployment.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=60)
            await logger.awarning(
                "router.circuit_open",
                deployment=deployment.name,
                failures=deployment.consecutive_failures,
                cooldown_until=deployment.cooldown_until.isoformat(),
            )

        await db.flush()

    async def mark_success(
        self,
        deployment: ModelDeployment,
        db: AsyncSession,
    ) -> None:
        """Reset failure counters on successful request."""
        if deployment.consecutive_failures > 0:
            deployment.consecutive_failures = 0
            deployment.is_healthy = True
            deployment.cooldown_until = None
            await db.flush()