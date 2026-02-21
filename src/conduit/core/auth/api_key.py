"""API key validation and access control checks."""

from __future__ import annotations

from decimal import Decimal

from conduit.common.errors import BudgetExceededError, ModelNotAllowedError
from conduit.models.api_key import APIKey


def check_model_access(api_key: APIKey, model: str) -> None:
    """Verify that an API key is allowed to access a given model."""
    if api_key.allowed_models is None:
        return  # No restrictions

    if model not in api_key.allowed_models:
        raise ModelNotAllowedError(
            f"API key '{api_key.key_prefix}...' is not allowed to access model '{model}'. "
            f"Allowed models: {api_key.allowed_models}",
        )


def check_budget(api_key: APIKey) -> None:
    """Verify that an API key has not exceeded its budget."""
    if api_key.budget_limit_usd is None:
        return  # No budget limit

    if api_key.spend_usd >= api_key.budget_limit_usd:
        raise BudgetExceededError(
            f"API key '{api_key.key_prefix}...' has exceeded its budget. "
            f"Spent: ${api_key.spend_usd}, Limit: ${api_key.budget_limit_usd}",
        )