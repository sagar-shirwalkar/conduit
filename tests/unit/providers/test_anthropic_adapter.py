"""Tests for the Anthropic provider adapter."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from conduit.common.crypto import encrypt_value
from conduit.models.deployment import ModelDeployment, ProviderType
from conduit.providers.anthropic import AnthropicAdapter
from conduit.schemas.completion import ChatCompletionRequest, ChatMessage


def _make_deployment() -> ModelDeployment:
    d = ModelDeployment.__new__(ModelDeployment)
    d.id = uuid.uuid4()
    d.name = "test-anthropic"
    d.provider = ProviderType.ANTHROPIC
    d.model_name = "claude-4-6-sonnet-20251101"
    d.api_base = "https://api.anthropic.com"
    d.api_key_encrypted = encrypt_value("sk-ant-test")
    return d


def _make_request(**kwargs) -> ChatCompletionRequest:
    defaults = {
        "model": "claude-4-6-sonnet-20251101",
        "messages": [ChatMessage(role="user", content="Hello")],
    }
    defaults.update(kwargs)
    return ChatCompletionRequest(**defaults)


@pytest.mark.unit
class TestAnthropicAdapter:
    def test_system_message_extracted(self) -> None:
        adapter = AnthropicAdapter(MagicMock())
        request = _make_request(
            messages=[
                ChatMessage(role="system", content="You are helpful."),
                ChatMessage(role="user", content="Hi"),
            ]
        )
        url, headers, body = adapter.transform_request(request, _make_deployment())

        assert body["system"] == "You are helpful."
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "user"

    def test_no_system_message(self) -> None:
        adapter = AnthropicAdapter(MagicMock())
        request = _make_request()
        _, _, body = adapter.transform_request(request, _make_deployment())

        assert "system" not in body

    def test_url_and_headers(self) -> None:
        adapter = AnthropicAdapter(MagicMock())
        request = _make_request()
        url, headers, body = adapter.transform_request(request, _make_deployment())

        assert url == "https://api.anthropic.com/v1/messages"
        assert "x-api-key" in headers
        assert "anthropic-version" in headers

    def test_max_tokens_default(self) -> None:
        adapter = AnthropicAdapter(MagicMock())
        request = _make_request()
        _, _, body = adapter.transform_request(request, _make_deployment())
        assert body["max_tokens"] == 4096

    def test_max_tokens_override(self) -> None:
        adapter = AnthropicAdapter(MagicMock())
        request = _make_request(max_tokens=256)
        _, _, body = adapter.transform_request(request, _make_deployment())
        assert body["max_tokens"] == 256

    def test_stop_sequences_mapping(self) -> None:
        adapter = AnthropicAdapter(MagicMock())
        request = _make_request(stop=["END", "STOP"])
        _, _, body = adapter.transform_request(request, _make_deployment())
        assert body["stop_sequences"] == ["END", "STOP"]

    def test_consecutive_roles_merged(self) -> None:
        adapter = AnthropicAdapter(MagicMock())
        request = _make_request(
            messages=[
                ChatMessage(role="user", content="Hello"),
                ChatMessage(role="user", content="Are you there?"),
            ]
        )
        _, _, body = adapter.transform_request(request, _make_deployment())
        assert len(body["messages"]) == 1
        assert "Hello" in body["messages"][0]["content"]
        assert "Are you there?" in body["messages"][0]["content"]

    def test_transform_response(self) -> None:
        adapter = AnthropicAdapter(MagicMock())
        raw = {
            "id": "msg_123",
            "type": "message",
            "content": [{"type": "text", "text": "Hello!"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        response = adapter.transform_response(raw, "claude-4-6-sonnet-20241022")

        assert response.choices[0].message.content == "Hello!"
        assert response.choices[0].finish_reason == "stop"
        assert response.usage.prompt_tokens == 10
        assert response.usage.completion_tokens == 5
        assert response.usage.total_tokens == 15

    def test_transform_response_with_tool_use(self) -> None:
        adapter = AnthropicAdapter(MagicMock())
        raw = {
            "id": "msg_456",
            "type": "message",
            "content": [
                {"type": "text", "text": "Let me check that."},
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "get_weather",
                    "input": {"city": "London"},
                },
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 20, "output_tokens": 30},
        }
        response = adapter.transform_response(raw, "claude-4-6-sonnet-20241022")

        assert response.choices[0].message.content == "Let me check that."
        assert response.choices[0].message.tool_calls is not None
        assert len(response.choices[0].message.tool_calls) == 1
        assert response.choices[0].message.tool_calls[0]["function"]["name"] == "get_weather"
        assert response.choices[0].finish_reason == "tool_calls"

    def test_stop_reason_mapping(self) -> None:
        assert AnthropicAdapter._map_stop_reason("end_turn") == "stop"
        assert AnthropicAdapter._map_stop_reason("max_tokens") == "length"
        assert AnthropicAdapter._map_stop_reason("tool_use") == "tool_calls"
        assert AnthropicAdapter._map_stop_reason("stop_sequence") == "stop"
        assert AnthropicAdapter._map_stop_reason(None) == "stop"