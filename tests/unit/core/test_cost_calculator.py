"""Tests for cost calculation."""

from decimal import Decimal

import pytest

from conduit.core.cost.calculator import calculate_cost


@pytest.mark.unit
class TestCostCalculator:
    def test_gpt4o_cost(self) -> None:
        cost = calculate_cost("gpt-4o", prompt_tokens=1000, completion_tokens=500)
        # input: 1000 * 2.50 / 1M = 0.0025
        # output: 500 * 10.00 / 1M = 0.005
        # total: 0.0075
        assert cost == Decimal("0.00750000")

    def test_gpt4o_mini_cost(self) -> None:
        cost = calculate_cost("gpt-4o-mini", prompt_tokens=10000, completion_tokens=1000)
        # input: 10000 * 0.15 / 1M = 0.0015
        # output: 1000 * 0.60 / 1M = 0.0006
        # total: 0.0021
        assert cost == Decimal("0.00210000")

    def test_unknown_model_returns_zero(self) -> None:
        cost = calculate_cost("unknown-model", prompt_tokens=1000, completion_tokens=500)
        assert cost == Decimal("0")

    def test_zero_tokens(self) -> None:
        cost = calculate_cost("gpt-4o", prompt_tokens=0, completion_tokens=0)
        assert cost == Decimal("0E-8")