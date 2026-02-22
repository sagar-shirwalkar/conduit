"""Integration tests for provider fallback."""

from __future__ import annotations

import pytest
import respx
from httpx import AsyncClient, Response

from conduit.common.crypto import encrypt_value
from conduit.models.deployment import ModelDeployment, ProviderType


MOCK_COMPLETION = {
    "id": "chatcmpl-fallback",
    "object": "chat.completion",
    "created": 1700000000,
    "model": "gpt-5",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "From backup!"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
}


@pytest.fixture
async def _seed_fallback_deployments(db_session) -> None:
    """Create primary (will fail) and backup (will succeed) deployments."""
    primary = ModelDeployment(
        name="primary-openai",
        provider=ProviderType.OPENAI,
        model_name="gpt-5",
        api_base="https://primary.openai.com/v1",
        api_key_encrypted=encrypt_value("sk-primary"),
        priority=1,
        weight=100,
        is_active=True,
        is_healthy=True,
    )
    backup = ModelDeployment(
        name="backup-openai",
        provider=ProviderType.OPENAI,
        model_name="gpt-5",
        api_base="https://backup.openai.com/v1",
        api_key_encrypted=encrypt_value("sk-backup"),
        priority=2,
        weight=100,
        is_active=True,
        is_healthy=True,
    )
    db_session.add_all([primary, backup])
    await db_session.commit()


@pytest.mark.integration
class TestFallback:
    @respx.mock
    async def test_fallback_on_provider_error(
        self,
        client: AsyncClient,
        admin_headers: dict,
        _seed_fallback_deployments: None,
    ) -> None:
        """If the primary provider fails, should fallback to backup."""
        # Primary returns 500
        respx.post("https://primary.openai.com/v1/chat/completions").mock(
            return_value=Response(500, json={"error": {"message": "Internal error"}})
        )
        # Backup succeeds
        respx.post("https://backup.openai.com/v1/chat/completions").mock(
            return_value=Response(200, json=MOCK_COMPLETION)
        )

        response = await client.post(
            "/v1/chat/completions",
            headers=admin_headers,
            json={
                "model": "gpt-5",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["choices"][0]["message"]["content"] == "From backup!"

    @respx.mock
    async def test_all_providers_fail(
        self,
        client: AsyncClient,
        admin_headers: dict,
        _seed_fallback_deployments: None,
    ) -> None:
        """If all providers fail, should return 502 error."""
        respx.post("https://primary.openai.com/v1/chat/completions").mock(
            return_value=Response(500, json={"error": {"message": "Primary down"}})
        )
        respx.post("https://backup.openai.com/v1/chat/completions").mock(
            return_value=Response(500, json={"error": {"message": "Backup down"}})
        )

        response = await client.post(
            "/v1/chat/completions",
            headers=admin_headers,
            json={
                "model": "gpt-5",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        assert response.status_code == 502