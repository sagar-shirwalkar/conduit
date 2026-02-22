"""
Anthropic provider adapter (Messages API)

Handles key differences from OpenAI:
  - System message is a top-level field, not in messages array
  - Role mapping: "assistant" stays, but no "system" in messages
  - Response format: content blocks (text, tool_use)
  - Streaming: message_start -> content_block_delta -> message_delta -> message_stop
  - Auth: x-api-key header instead of Authorization: Bearer
  - Usage: input_tokens / output_tokens (not prompt_tokens / completion_tokens)
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator

import httpx
import structlog

from conduit.common.crypto import decrypt_value
from conduit.common.errors import ProviderError
from conduit.models.deployment import ModelDeployment
from conduit.providers.base import ProviderAdapter
from conduit.schemas.completion import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    StreamChoice,
    Usage,
)

logger = structlog.stdlib.get_logger()

ANTHROPIC_API_VERSION = "2024-01-01"
DEFAULT_MAX_TOKENS = 4096


class AnthropicAdapter(ProviderAdapter):
    provider_name = "anthropic"

    # Request Transform
    def transform_request(
        self,
        request: ChatCompletionRequest,
        deployment: ModelDeployment,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        url = f"{deployment.api_base}/v1/messages"

        headers = {
            "x-api-key": decrypt_value(deployment.api_key_encrypted),
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }

        # Separate system message from conversation
        system_content: str | None = None
        messages: list[dict[str, Any]] = []

        for msg in request.messages:
            if msg.role == "system":
                # Anthropic supports a single system string or list of blocks
                if isinstance(msg.content, str):
                    system_content = msg.content
                elif isinstance(msg.content, list):
                    # Extract text from content blocks
                    system_content = " ".join(
                        block.get("text", "") for block in msg.content if isinstance(block, dict)
                    )
            else:
                anthropic_msg = self._transform_message(msg)
                messages.append(anthropic_msg)

        # Merge consecutive messages with the same role (Anthropic requirement)
        messages = self._merge_consecutive_roles(messages)

        body: dict[str, Any] = {
            "model": deployment.model_name,
            "messages": messages,
            "max_tokens": request.max_tokens or DEFAULT_MAX_TOKENS,
        }

        if system_content:
            body["system"] = system_content
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.stop:
            body["stop_sequences"] = (
                request.stop if isinstance(request.stop, list) else [request.stop]
            )
        if request.stream:
            body["stream"] = True

        # Tool use mapping
        if request.tools:
            body["tools"] = [self._transform_tool(t) for t in request.tools]

        return url, headers, body

    @staticmethod
    def _transform_message(msg: ChatMessage) -> dict[str, Any]:
        """Convert an OpenAI message to Anthropic format."""
        role = msg.role
        if role == "tool":
            # Tool results in Anthropic use role "user" with tool_result content
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id or "",
                        "content": msg.content or "",
                    }
                ],
            }

        content: Any
        if isinstance(msg.content, str):
            content = msg.content
        elif isinstance(msg.content, list):
            content = [AnthropicAdapter._transform_content_block(b) for b in msg.content]
        else:
            content = msg.content or ""

        result: dict[str, Any] = {"role": role, "content": content}

        # Handle tool calls from assistant
        if msg.tool_calls:
            blocks = []
            if isinstance(content, str) and content:
                blocks.append({"type": "text", "text": content})
            for tc in msg.tool_calls:
                func = tc.get("function", {})
                tool_input = func.get("arguments", "{}")
                if isinstance(tool_input, str):
                    try:
                        tool_input = json.loads(tool_input)
                    except json.JSONDecodeError:
                        tool_input = {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "input": tool_input,
                })
            result["content"] = blocks

        return result

    @staticmethod
    def _transform_content_block(block: dict[str, Any]) -> dict[str, Any]:
        """Convert an OpenAI content block to Anthropic format."""
        if block.get("type") == "text":
            return {"type": "text", "text": block.get("text", "")}
        if block.get("type") == "image_url":
            url_data = block.get("image_url", {})
            url = url_data.get("url", "")
            # Handle base64 data URIs
            if url.startswith("data:"):
                parts = url.split(",", 1)
                media_type = parts[0].replace("data:", "").replace(";base64", "")
                data = parts[1] if len(parts) > 1 else ""
                return {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": data,
                    },
                }
            return {
                "type": "image",
                "source": {"type": "url", "url": url},
            }
        return block

    @staticmethod
    def _transform_tool(tool: dict[str, Any]) -> dict[str, Any]:
        """Convert OpenAI tool definition to Anthropic format."""
        func = tool.get("function", {})
        return {
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {}),
        }

    @staticmethod
    def _merge_consecutive_roles(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Anthropic requires alternating user/assistant roles. Merge consecutive same-role."""
        if not messages:
            return messages

        merged: list[dict[str, Any]] = [messages[0]]
        for msg in messages[1:]:
            if msg["role"] == merged[-1]["role"]:
                # Merge content
                prev_content = merged[-1]["content"]
                curr_content = msg["content"]

                if isinstance(prev_content, str) and isinstance(curr_content, str):
                    merged[-1]["content"] = prev_content + "\n" + curr_content
                elif isinstance(prev_content, list) and isinstance(curr_content, list):
                    merged[-1]["content"] = prev_content + curr_content
                elif isinstance(prev_content, str) and isinstance(curr_content, list):
                    merged[-1]["content"] = [{"type": "text", "text": prev_content}] + curr_content
                elif isinstance(prev_content, list) and isinstance(curr_content, str):
                    merged[-1]["content"] = prev_content + [{"type": "text", "text": curr_content}]
            else:
                merged.append(msg)

        return merged

    # Response Transform
    def transform_response(
        self,
        raw_response: dict[str, Any],
        model: str,
    ) -> ChatCompletionResponse:
        # Extract text from content blocks
        content_blocks = raw_response.get("content", [])
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })

        message = ChatMessage(
            role="assistant",
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls if tool_calls else None,
        )

        raw_usage = raw_response.get("usage", {})
        input_tokens = raw_usage.get("input_tokens", 0)
        output_tokens = raw_usage.get("output_tokens", 0)

        return ChatCompletionResponse(
            id=f"chatcmpl-{raw_response.get('id', uuid.uuid4().hex[:24])}",
            created=int(time.time()),
            model=model,
            choices=[
                Choice(
                    index=0,
                    message=message,
                    finish_reason=self._map_stop_reason(raw_response.get("stop_reason")),
                )
            ],
            usage=Usage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
        )

    @staticmethod
    def _map_stop_reason(stop_reason: str | None) -> str:
        """Map Anthropic stop reasons to OpenAI finish reasons."""
        mapping = {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "max_tokens": "length",
            "tool_use": "tool_calls",
        }
        return mapping.get(stop_reason or "", "stop")

    # ── Non-Streaming ───────────────────────────────────

    async def send(
        self,
        request: ChatCompletionRequest,
        deployment: ModelDeployment,
    ) -> ChatCompletionResponse:
        url, headers, body = self.transform_request(request, deployment)
        body["stream"] = False

        try:
            response = await self.client.post(url, headers=headers, json=body, timeout=120.0)
        except httpx.TimeoutException as e:
            raise ProviderError(
                f"Anthropic request timed out: {e}",
                details={"provider": "anthropic", "deployment": deployment.name},
            ) from e
        except httpx.ConnectError as e:
            raise ProviderError(
                f"Failed to connect to Anthropic: {e}",
                details={"provider": "anthropic", "deployment": deployment.name},
            ) from e

        if response.status_code != 200:
            await self._handle_error_response(response, deployment)

        return self.transform_response(response.json(), request.model)

    # Streaming
    async def stream(
        self,
        request: ChatCompletionRequest,
        deployment: ModelDeployment,
    ) -> AsyncIterator[ChatCompletionChunk]:
        """
        Stream Anthropic Messages API → OpenAI-compatible chunks.

        Anthropic events:
          message_start       → contains message id, model, usage.input_tokens
          content_block_start → new content block
          content_block_delta → text delta
          content_block_stop  → block complete
          message_delta       → stop_reason, usage.output_tokens
          message_stop        → done
        """
        url, headers, body = self.transform_request(request, deployment)
        body["stream"] = True

        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())
        input_tokens = 0
        output_tokens = 0

        try:
            async with self.client.stream(
                "POST", url, headers=headers, json=body, timeout=120.0
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    await self._handle_error_response(response, deployment)

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    data = line[6:].strip()
                    if not data:
                        continue

                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")

                    if event_type == "message_start":
                        msg = event.get("message", {})
                        chunk_id = f"chatcmpl-{msg.get('id', uuid.uuid4().hex[:24])}"
                        usage = msg.get("usage", {})
                        input_tokens = usage.get("input_tokens", 0)

                        # Emit initial chunk (role)
                        yield ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[
                                StreamChoice(
                                    index=0,
                                    delta={"role": "assistant", "content": ""},
                                    finish_reason=None,
                                )
                            ],
                        )

                    elif event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            yield ChatCompletionChunk(
                                id=chunk_id,
                                created=created,
                                model=request.model,
                                choices=[
                                    StreamChoice(
                                        index=0,
                                        delta={"content": text},
                                        finish_reason=None,
                                    )
                                ],
                            )

                    elif event_type == "message_delta":
                        delta = event.get("delta", {})
                        usage = event.get("usage", {})
                        output_tokens = usage.get("output_tokens", 0)
                        stop_reason = self._map_stop_reason(delta.get("stop_reason"))

                        # Emit final chunk with finish_reason and usage
                        yield ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=request.model,
                            choices=[
                                StreamChoice(
                                    index=0,
                                    delta={},
                                    finish_reason=stop_reason,
                                )
                            ],
                            usage=Usage(
                                prompt_tokens=input_tokens,
                                completion_tokens=output_tokens,
                                total_tokens=input_tokens + output_tokens,
                            ),
                        )

                    elif event_type == "message_stop":
                        break

        except httpx.TimeoutException as e:
            raise ProviderError(
                f"Anthropic stream timed out: {e}",
                details={"provider": "anthropic", "deployment": deployment.name},
            ) from e