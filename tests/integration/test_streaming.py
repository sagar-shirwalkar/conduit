"""Integration tests for SSE streaming completions."""

from __future__ import annotations

import json

import pytest
import respx
from httpx import AsyncClient, Response

from conduit.common.crypto import encrypt_value
from conduit.models.deployment import ModelDeployment, ProviderType


@pytest.fixture
async def _seed_openai_deployment(db_session) -> None:
    """Seed a test OpenAI deployment."""
    deployment = ModelDeployment(
        name="stream-test-openai",
        provider=ProviderType.OPENAI,
        model_name="gpt-5",
        api_base="https://api.openai.com/v1",
        api_key_encrypted=encrypt_value("sk-test"),
        priority=1,
        weight=100,
        is_active=True,
        is_healthy=True,
    )
    db_session.add(deployment)
    await db_session.commit()


MOCK_SSE_RESPONSE = (
    'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1700000000,'
    '"model":"gpt-5","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}\n\n'
    'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1700000000,'
    '"model":"gpt-5","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}\n\n'
    'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1700000000,'
    '"model":"gpt-5","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}\n\n'
    'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1700000000,'
    '"model":"gpt-5","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],'
    '"usage":{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12}}\n\n'
    "data: [DONE]\n\n"
)


@pytest.mark.integration
class TestStreaming:
    @respx.mock
    async def test_streaming_returns_sse(
        self, client: AsyncClient, admin_headers: dict, _seed_openai_deployment: None
    ) -> None:
        # Mock OpenAI streaming endpoint
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                content=MOCK_SSE_RESPONSE,
                headers={"content-type": "text/event-stream"},
            )
        )

        response = await client.post(
            "/v1/chat/completions",
            headers=admin_headers,
            json={
                "model": "gpt-5",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        assert response.headers.get("x-conduit-request-id") is not None

        # Parse SSE events from response body
        body = response.text
        events = [line for line in body.split("\n") if line.startswith("data: ")]

        # Should have at least the content chunks + [DONE]
        assert len(events) >= 3
        assert events[-1] == "data: [DONE]"

        # Parse a content chunk
        first_data = json.loads(events[0][6:])
        assert first_data["object"] == "chat.completion.chunk"

    @respx.mock
    async def test_streaming_content_assembly(
        self, client: AsyncClient, admin_headers: dict, _seed_openai_deployment: None
    ) -> None:
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                content=MOCK_SSE_RESPONSE,
                headers={"content-type": "text/event-stream"},
            )
        )

        response = await client.post(
            "/v1/chat/completions",
            headers=admin_headers,
            json={
                "model": "gpt-5",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
        )

        # Extract all content deltas
        body = response.text
        content = ""
        for line in body.split("\n"):
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            event = json.loads(line[6:])
            for choice in event.get("choices", []):
                delta_content = choice.get("delta", {}).get("content", "")
                if delta_content:
                    content += delta_content

        assert content == "Hello!"

    async def test_streaming_auth_required(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-5",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
        )
        # Auth failure should happen BEFORE streaming starts
        assert response.status_code == 401