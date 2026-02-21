"""Token-based cost calculation."""

from __future__ import annotations

from decimal import Decimal

from conduit.core.cost.pricing import get_model_pricing


def calculate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal:
    """
    Calculate the cost of a request in USD.

    Uses the pricing table from config/pricing/models.json.
    Returns Decimal("0") for unknown models.
    """
    pricing = get_model_pricing(model)
    if pricing is None:
        return Decimal("0")

    input_cost = Decimal(str(pricing["input_cost_per_1m"])) * Decimal(prompt_tokens) / Decimal("1000000")
    output_cost = Decimal(str(pricing["output_cost_per_1m"])) * Decimal(completion_tokens) / Decimal("1000000")

    return (input_cost + output_cost).quantize(Decimal("0.00000001"))