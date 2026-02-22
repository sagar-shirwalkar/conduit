"""Tests for the router engine and strategies."""

from __future__ import annotations

import uuid

import pytest

from conduit.core.router.strategies import (
    CostStrategy,
    PriorityStrategy,
    WeightedRoundRobinStrategy,
)
from conduit.models.deployment import ModelDeployment, ProviderType


def _make_deployment(name: str, priority: int = 1, weight: int = 100, **kw) -> ModelDeployment:
    d = ModelDeployment.__new__(ModelDeployment)
    d.id = uuid.uuid4()
    d.name = name
    d.provider = ProviderType.OPENAI
    d.model_name = kw.get("model_name", "gpt-5")
    d.api_base = "https://api.openai.com/v1"
    d.api_key_encrypted = "enc"
    d.priority = priority
    d.weight = weight
    d.is_active = True
    d.is_healthy = True
    d.cooldown_until = None
    d.consecutive_failures = 0
    d.max_rpm = None
    d.max_tpm = None
    return d


@pytest.mark.unit
class TestPriorityStrategy:
    def test_sorts_by_priority_ascending(self) -> None:
        s = PriorityStrategy()
        deploys = [
            _make_deployment("c", priority=3),
            _make_deployment("a", priority=1),
            _make_deployment("b", priority=2),
        ]
        ranked = s.rank(deploys)
        assert [d.name for d in ranked] == ["a", "b", "c"]

    def test_empty_list(self) -> None:
        s = PriorityStrategy()
        assert s.rank([]) == []


@pytest.mark.unit
class TestWeightedRoundRobinStrategy:
    def test_all_deployments_appear(self) -> None:
        s = WeightedRoundRobinStrategy()
        deploys = [
            _make_deployment("a", weight=100),
            _make_deployment("b", weight=50),
            _make_deployment("c", weight=10),
        ]
        ranked = s.rank(deploys)
        assert set(d.name for d in ranked) == {"a", "b", "c"}

    def test_higher_weight_tends_to_be_first(self) -> None:
        """Statistical test — high weight should appear first most often."""
        s = WeightedRoundRobinStrategy()
        deploys = [
            _make_deployment("heavy", weight=1000),
            _make_deployment("light", weight=1),
        ]
        first_counts: dict[str, int] = {"heavy": 0, "light": 0}
        for _ in range(100):
            ranked = s.rank(deploys)
            first_counts[ranked[0].name] += 1

        assert first_counts["heavy"] > 80  # Should be ~99%


@pytest.mark.unit
class TestCostStrategy:
    def test_sorts_by_output_cost(self) -> None:
        s = CostStrategy()
        deploys = [
            _make_deployment("expensive", model_name="gpt-5"),       # output: 10.00
            _make_deployment("cheap", model_name="gpt-5-mini"),      # output: 0.60
        ]
        ranked = s.rank(deploys)
        assert ranked[0].name == "cheap"
        assert ranked[1].name == "expensive"

    def test_unknown_model_goes_last(self) -> None:
        s = CostStrategy()
        deploys = [
            _make_deployment("unknown", model_name="custom-model"),
            _make_deployment("known", model_name="gpt-5-mini"),
        ]
        ranked = s.rank(deploys)
        assert ranked[0].name == "known"
        assert ranked[1].name == "unknown"