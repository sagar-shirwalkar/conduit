"""
Routing strategies for selecting deployments.

Each strategy takes a list of candidate deployments and returns
them in the preferred order of execution (first = most preferred).
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

import structlog

from conduit.core.cost.pricing import get_model_pricing
from conduit.models.deployment import ModelDeployment

logger = structlog.stdlib.get_logger()


class RoutingStrategy(ABC):
    """Base class for routing strategies."""

    name: str

    @abstractmethod
    def rank(self, deployments: list[ModelDeployment]) -> list[ModelDeployment]:
        """Return deployments sorted by preference (best first)."""
        ...


class PriorityStrategy(RoutingStrategy):
    """Select deployments by explicit priority (lower number = higher priority)."""

    name = "priority"

    def rank(self, deployments: list[ModelDeployment]) -> list[ModelDeployment]:
        return sorted(deployments, key=lambda d: d.priority)


class WeightedRoundRobinStrategy(RoutingStrategy):
    """
    Weighted random selection.

    Deployments with higher weights are proportionally more likely
    to be selected, but the list is shuffled each time to distribute load.
    """

    name = "round_robin"

    def rank(self, deployments: list[ModelDeployment]) -> list[ModelDeployment]:
        if not deployments:
            return deployments

        # Weighted shuffle using random.choices for the first pick,
        # then fall back to priority for remaining
        weights = [d.weight for d in deployments]
        total = sum(weights)

        if total == 0:
            return deployments

        # Build weighted ordering
        remaining = list(deployments)
        ordered: list[ModelDeployment] = []

        while remaining:
            w = [d.weight for d in remaining]
            chosen = random.choices(remaining, weights=w, k=1)[0]
            ordered.append(chosen)
            remaining.remove(chosen)

        return ordered


class CostStrategy(RoutingStrategy):
    """Select the cheapest deployment (by output token cost)."""

    name = "cost"

    def rank(self, deployments: list[ModelDeployment]) -> list[ModelDeployment]:
        def cost_key(d: ModelDeployment) -> float:
            pricing = get_model_pricing(d.model_name)
            if pricing is None:
                return float("inf")
            return pricing.get("output_cost_per_1m", float("inf"))

        return sorted(deployments, key=cost_key)


class LatencyStrategy(RoutingStrategy):
    """
    Select deployment likely to have lowest latency.

    Phase 2: Uses priority as proxy (production would use p50 historical latency).
    Phase 3 will integrate actual latency percentiles from request logs.
    """

    name = "latency"

    def rank(self, deployments: list[ModelDeployment]) -> list[ModelDeployment]:
        # TODO Phase 3: rank by historical p50 latency from request_logs
        return sorted(deployments, key=lambda d: d.priority)


# Strategy Registry

_STRATEGIES: dict[str, RoutingStrategy] = {
    "priority": PriorityStrategy(),
    "round_robin": WeightedRoundRobinStrategy(),
    "cost": CostStrategy(),
    "latency": LatencyStrategy(),
}


def get_strategy(name: str) -> RoutingStrategy:
    """Get a routing strategy by name."""
    strategy = _STRATEGIES.get(name)
    if strategy is None:
        return _STRATEGIES["priority"]  # Safe default
    return strategy