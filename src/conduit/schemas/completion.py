"""OpenAI-compatible chat completion request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible /v1/chat/completions request."""

    model: str = Field(..., description="Model identifier or Conduit alias")
    messages: list[ChatMessage] = Field(..., min_length=1)
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    top_p: float | None = Field(None, ge=0.0, le=1.0)
    n: int | None = Field(1, ge=1, le=10)
    stream: bool = False
    stop: str | list[str] | None = None
    max_tokens: int | None = Field(None, ge=1)
    presence_penalty: float | None = Field(None, ge=-2.0, le=2.0)
    frequency_penalty: float | None = Field(None, ge=-2.0, le=2.0)
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    seed: int | None = None
    user: str | None = None

    model_config = {"populate_by_name": True}


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Choice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible response."""

    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage


class StreamChoice(BaseModel):
    index: int
    delta: dict[str, Any]
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    """OpenAI-compatible streaming chunk."""

    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[StreamChoice]