"""
Router engine — selects deployments and manages fallback chains.

The router returns an ordered list of deployments to try. The
completion service iterates through them, falling back on failure.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.common.errors import NoHealthyDeploymentError
from conduit.config import get_settings
from conduit.core.router.health import CircuitBreaker
from conduit.core.router.strategies import get_strategy
from conduit.models.deployment import ModelDeployment

logger = structlog.stdlib.get_logger()


class RouterEngine:
    """Selects and ranks deployments for a given model request."""

    def __init__(
        self,
        strategy_name: str | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        settings = get_settings()
        self.strategy_name = strategy_name or settings.routing.default_strategy
        self.fallback_enabled = settings.routing.fallback_enabled
        self.max_retries = settings.routing.max_retries
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

    async def route(
        self,
        model: str,
        db: AsyncSession,
    ) -> list[ModelDeployment]:
        """
        Find and rank all viable deployments for the requested model.

        Returns:
            Ordered list of deployments to try (best first).
            The completion service will iterate with fallback.

        Raises:
            NoHealthyDeploymentError: If no deployment is available.
        """
        result = await db.execute(
            select(ModelDeployment)
            .where(
                ModelDeployment.model_name == model,
                ModelDeployment.is_active.is_(True),
            )
        )
        all_deployments = list(result.scalars().all())

        if not all_deployments:
            raise NoHealthyDeploymentError(
                f"No deployments configured for model '{model}'. "
                f"Register one via POST /admin/v1/models/deployments"
            )

        # Filter through circuit breaker
        available = [d for d in all_deployments if self.circuit_breaker.is_available(d)]

        if not available:
            raise NoHealthyDeploymentError(
                f"All deployments for model '{model}' are currently unhealthy. "
                f"Total deployments: {len(all_deployments)}, "
                f"all in cooldown."
            )

        # Apply routing strategy to rank available deployments
        strategy = get_strategy(self.strategy_name)
        ranked = strategy.rank(available)

        # Limit to max_retries + 1 (first attempt + retries)
        if not self.fallback_enabled:
            ranked = ranked[:1]
        else:
            ranked = ranked[: self.max_retries + 1]

        await logger.ainfo(
            "router.ranked",
            model=model,
            strategy=self.strategy_name,
            candidates=[d.name for d in ranked],
            total_available=len(available),
            total_configured=len(all_deployments),
        )

        return ranked

    async def record_success(
        self,
        deployment: ModelDeployment,
        db: AsyncSession,
    ) -> None:
        """Record a successful request."""
        await self.circuit_breaker.record_success(deployment, db)

    async def record_failure(
        self,
        deployment: ModelDeployment,
        db: AsyncSession,
    ) -> None:
        """Record a failed request."""
        await self.circuit_breaker.record_failure(deployment, db)