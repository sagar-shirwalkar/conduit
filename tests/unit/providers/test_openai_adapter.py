"""Tests for the OpenAI provider adapter."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from conduit.common.crypto import encrypt_value
from conduit.models.deployment import ModelDeployment, ProviderType
from conduit.providers.openai import OpenAIAdapter
from conduit.schemas.completion import ChatCompletionRequest, ChatMessage


@pytest.mark.unit
class TestOpenAIAdapter:
    def _make_deployment(self) -> ModelDeployment:
        d = ModelDeployment.__new__(ModelDeployment)
        d.id = uuid.uuid4()
        d.name = "test-openai"
        d.provider = ProviderType.OPENAI
        d.model_name = "gpt-4o"
        d.api_base = "https://api.openai.com/v1"
        d.api_key_encrypted = encrypt_value("sk-test")
        return d

    def _make_request(self, **kwargs) -> ChatCompletionRequest:
        defaults = {
            "model": "gpt-4o",
            "messages": [ChatMessage(role="user", content="Hello")],
        }
        defaults.update(kwargs)
        return ChatCompletionRequest(**defaults)

    def test_transform_request_basic(self) -> None:
        adapter = OpenAIAdapter(MagicMock())
        deployment = self._make_deployment()
        request = self._make_request()

        url, headers, body = adapter.transform_request(request, deployment)

        assert url == "https://api.openai.com/v1/chat/completions"
        assert "Authorization" in headers
        assert body["model"] == "gpt-4o"
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "user"

    def test_transform_request_with_optional_params(self) -> None:
        adapter = OpenAIAdapter(MagicMock())
        deployment = self._make_deployment()
        request = self._make_request(temperature=0.7, max_tokens=100, top_p=0.9)

        _, _, body = adapter.transform_request(request, deployment)

        assert body["temperature"] == 0.7
        assert body["max_tokens"] == 100
        assert body["top_p"] == 0.9

    def test_transform_response(self) -> None:
        adapter = OpenAIAdapter(MagicMock())

        raw = {
            "id": "chatcmpl-abc123",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "gpt-4o",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Hello! How can I help?",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 8,
                "total_tokens": 18,
            },
        }

        response = adapter.transform_response(raw, "gpt-4o")

        assert response.id == "chatcmpl-abc123"
        assert response.model == "gpt-4o"
        assert len(response.choices) == 1
        assert response.choices[0].message.content == "Hello! How can I help?"
        assert response.usage.prompt_tokens == 10
        assert response.usage.completion_tokens == 8
        assert response.usage.total_tokens == 18