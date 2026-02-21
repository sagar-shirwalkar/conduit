"""Test data factories."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from conduit.common.crypto import encrypt_value, generate_api_key, hash_api_key
from conduit.models.api_key import APIKey
from conduit.models.deployment import ModelDeployment, ProviderType
from conduit.models.user import User, UserRole


def create_test_user(
    email: str = "test@example.com",
    role: UserRole = UserRole.MEMBER,
) -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        role=role,
    )


def create_test_api_key(
    user_id: uuid.UUID,
    raw_key: str | None = None,
    budget_limit: Decimal | None = None,
    allowed_models: list[str] | None = None,
) -> tuple[str, APIKey]:
    """Returns (raw_key, api_key_model)."""
    if raw_key is None:
        raw_key, key_hash, key_prefix = generate_api_key()
    else:
        key_hash = hash_api_key(raw_key)
        key_prefix = raw_key[:12]

    return raw_key, APIKey(
        id=uuid.uuid4(),
        key_hash=key_hash,
        key_prefix=key_prefix,
        alias="test-key",
        user_id=user_id,
        budget_limit_usd=budget_limit,
        allowed_models=allowed_models,
        is_active=True,
    )


def create_test_deployment(
    name: str = "test-openai",
    provider: ProviderType = ProviderType.OPENAI,
    model_name: str = "gpt-4o",
    api_key: str = "sk-test-key",
) -> ModelDeployment:
    return ModelDeployment(
        id=uuid.uuid4(),
        name=name,
        provider=provider,
        model_name=model_name,
        api_base="https://api.openai.com/v1",
        api_key_encrypted=encrypt_value(api_key),
        priority=1,
        weight=100,
        is_active=True,
        is_healthy=True,
    )