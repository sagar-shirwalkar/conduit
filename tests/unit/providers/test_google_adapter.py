"""Tests for the Google Gemini provider adapter."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock

import pytest

from conduit.common.crypto import encrypt_value
from conduit.models.deployment import ModelDeployment, ProviderType
from conduit.providers.google import GoogleAdapter
from conduit.schemas.completion import ChatCompletionRequest, ChatMessage


def _make_deployment() -> ModelDeployment:
    d = ModelDeployment.__new__(ModelDeployment)
    d.id = uuid.uuid4()
    d.name = "test-gemini"
    d.provider = ProviderType.GOOGLE
    d.model_name = "gemini-3-pro"
    d.api_base = "https://generativelanguage.googleapis.com"
    d.api_key_encrypted = encrypt_value("AIza-test-key")
    return d


def _make_request(**kwargs) -> ChatCompletionRequest:
    defaults = {
        "model": "gemini-3-pro",
        "messages": [ChatMessage(role="user", content="Hello")],
    }
    defaults.update(kwargs)
    return ChatCompletionRequest(**defaults)


@pytest.mark.unit
class TestGoogleAdapter:
    def test_url_contains_model_and_key(self) -> None:
        adapter = GoogleAdapter(MagicMock())
        request = _make_request()
        url, _, _ = adapter.transform_request(request, _make_deployment())

        assert "gemini-3-pro" in url
        assert "generateContent" in url
        assert "key=" in url

    def test_streaming_url(self) -> None:
        adapter = GoogleAdapter(MagicMock())
        request = _make_request(stream=True)
        url, _, _ = adapter.transform_request(request, _make_deployment())

        assert "streamGenerateContent" in url
        assert "alt=sse" in url

    def test_system_message_as_system_instruction(self) -> None:
        adapter = GoogleAdapter(MagicMock())
        request = _make_request(
            messages=[
                ChatMessage(role="system", content="Be concise."),
                ChatMessage(role="user", content="Hi"),
            ]
        )
        _, _, body = adapter.transform_request(request, _make_deployment())

        assert "systemInstruction" in body
        assert body["systemInstruction"]["parts"][0]["text"] == "Be concise."
        assert len(body["contents"]) == 1
        assert body["contents"][0]["role"] == "user"

    def test_role_mapping(self) -> None:
        adapter = GoogleAdapter(MagicMock())
        request = _make_request(
            messages=[
                ChatMessage(role="user", content="Hi"),
                ChatMessage(role="assistant", content="Hello!"),
                ChatMessage(role="user", content="How are you?"),
            ]
        )
        _, _, body = adapter.transform_request(request, _make_deployment())

        assert body["contents"][0]["role"] == "user"
        assert body["contents"][1]["role"] == "model"
        assert body["contents"][2]["role"] == "user"

    def test_generation_config(self) -> None:
        adapter = GoogleAdapter(MagicMock())
        request = _make_request(temperature=0.5, top_p=0.9, max_tokens=100)
        _, _, body = adapter.transform_request(request, _make_deployment())

        gc = body["generationConfig"]
        assert gc["temperature"] == 0.5
        assert gc["topP"] == 0.9
        assert gc["maxOutputTokens"] == 100

    def test_json_response_format(self) -> None:
        adapter = GoogleAdapter(MagicMock())
        request = _make_request(response_format={"type": "json_object"})
        _, _, body = adapter.transform_request(request, _make_deployment())

        assert body["generationConfig"]["responseMimeType"] == "application/json"

    def test_tool_definitions(self) -> None:
        adapter = GoogleAdapter(MagicMock())
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather for a city",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                    },
                },
            }
        ]
        request = _make_request(tools=tools)
        _, _, body = adapter.transform_request(request, _make_deployment())

        decls = body["tools"][0]["functionDeclarations"]
        assert len(decls) == 1
        assert decls[0]["name"] == "get_weather"

    def test_transform_response(self) -> None:
        adapter = GoogleAdapter(MagicMock())
        raw = {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"text": "Hello! How can I help?"}],
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 8,
                "totalTokenCount": 18,
            },
        }
        response = adapter.transform_response(raw, "gemini-3-pro")

        assert response.choices[0].message.content == "Hello! How can I help?"
        assert response.choices[0].message.role == "assistant"
        assert response.choices[0].finish_reason == "stop"
        assert response.usage.prompt_tokens == 10
        assert response.usage.completion_tokens == 8

    def test_transform_response_with_function_call(self) -> None:
        adapter = GoogleAdapter(MagicMock())
        raw = {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "get_weather",
                                    "args": {"city": "London"},
                                }
                            }
                        ],
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 15,
                "candidatesTokenCount": 10,
                "totalTokenCount": 25,
            },
        }
        response = adapter.transform_response(raw, "gemini-3-pro")

        assert response.choices[0].message.tool_calls is not None
        tc = response.choices[0].message.tool_calls[0]
        assert tc["function"]["name"] == "get_weather"
        assert json.loads(tc["function"]["arguments"]) == {"city": "London"}

    def test_finish_reason_mapping(self) -> None:
        assert GoogleAdapter._map_finish_reason("STOP") == "stop"
        assert GoogleAdapter._map_finish_reason("MAX_TOKENS") == "length"
        assert GoogleAdapter._map_finish_reason("SAFETY") == "content_filter"
        assert GoogleAdapter._map_finish_reason(None) == "stop"