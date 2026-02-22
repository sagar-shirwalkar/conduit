"""
Google Gemini provider adapter (AI Studio + Vertex AI).

Handles key differences:
  - Endpoint: /v1beta/models/{model}:generateContent
  - Roles: "user" and "model" (not "assistant")
  - Message format: contents[].parts[].text
  - System instruction: separate field
  - Streaming: /v1beta/models/{model}:streamGenerateContent?alt=sse
  - Auth: API key as query param (AI Studio) or Bearer token (Vertex)
  - Usage: usageMetadata.promptTokenCount / candidatesTokenCount
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

# Gemini default base
DEFAULT_GEMINI_BASE = "https://generativelanguage.googleapis.com"


class GoogleAdapter(ProviderAdapter):
    provider_name = "google"

    # Request Transform

    def transform_request(
        self,
        request: ChatCompletionRequest,
        deployment: ModelDeployment,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        api_key = decrypt_value(deployment.api_key_encrypted)
        base = deployment.api_base.rstrip("/") or DEFAULT_GEMINI_BASE
        model = deployment.model_name

        # Determine endpoint based on streaming
        if request.stream:
            url = f"{base}/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}"
        else:
            url = f"{base}/v1beta/models/{model}:generateContent?key={api_key}"

        headers = {"Content-Type": "application/json"}

        # Build contents and separate system instruction
        system_instruction: dict[str, Any] | None = None
        contents: list[dict[str, Any]] = []

        for msg in request.messages:
            if msg.role == "system":
                text = msg.content if isinstance(msg.content, str) else str(msg.content)
                system_instruction = {"parts": [{"text": text}]}
            else:
                gemini_role = self._map_role_to_gemini(msg.role)
                parts = self._make_parts(msg)
                contents.append({"role": gemini_role, "parts": parts})

        body: dict[str, Any] = {"contents": contents}

        if system_instruction:
            body["systemInstruction"] = system_instruction

        # Generation config
        gen_config: dict[str, Any] = {}
        if request.temperature is not None:
            gen_config["temperature"] = request.temperature
        if request.top_p is not None:
            gen_config["topP"] = request.top_p
        if request.max_tokens is not None:
            gen_config["maxOutputTokens"] = request.max_tokens
        if request.stop:
            gen_config["stopSequences"] = (
                request.stop if isinstance(request.stop, list) else [request.stop]
            )
        if request.response_format:
            if request.response_format.get("type") == "json_object":
                gen_config["responseMimeType"] = "application/json"

        if gen_config:
            body["generationConfig"] = gen_config

        # Tool definitions
        if request.tools:
            body["tools"] = [{"functionDeclarations": self._transform_tools(request.tools)}]

        return url, headers, body

    @staticmethod
    def _map_role_to_gemini(role: str) -> str:
        mapping = {
            "user": "user",
            "assistant": "model",
            "tool": "user",  # Tool results come from "user" side in Gemini
        }
        return mapping.get(role, "user")

    @staticmethod
    def _map_role_from_gemini(role: str) -> str:
        mapping = {"model": "assistant", "user": "user"}
        return mapping.get(role, "assistant")

    @staticmethod
    def _make_parts(msg: ChatMessage) -> list[dict[str, Any]]:
        """Convert message content to Gemini parts."""
        if isinstance(msg.content, str):
            return [{"text": msg.content}]

        if isinstance(msg.content, list):
            parts: list[dict[str, Any]] = []
            for block in msg.content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    parts.append({"text": block.get("text", "")})
                elif block.get("type") == "image_url":
                    url_data = block.get("image_url", {})
                    url = url_data.get("url", "")
                    if url.startswith("data:"):
                        mime_parts = url.split(",", 1)
                        mime = mime_parts[0].replace("data:", "").replace(";base64", "")
                        data = mime_parts[1] if len(mime_parts) > 1 else ""
                        parts.append({
                            "inlineData": {"mimeType": mime, "data": data}
                        })
                    else:
                        parts.append({"fileData": {"fileUri": url}})
            return parts if parts else [{"text": ""}]

        # Function call results
        if msg.role == "tool" and msg.tool_call_id:
            return [{
                "functionResponse": {
                    "name": msg.name or msg.tool_call_id,
                    "response": {"result": msg.content or ""},
                }
            }]

        return [{"text": msg.content or ""}]

    @staticmethod
    def _transform_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI tool definitions to Gemini function declarations."""
        declarations = []
        for tool in tools:
            func = tool.get("function", {})
            decl: dict[str, Any] = {
                "name": func.get("name", ""),
                "description": func.get("description", ""),
            }
            params = func.get("parameters")
            if params:
                decl["parameters"] = params
            declarations.append(decl)
        return declarations

    # Response Transform

    def transform_response(
        self,
        raw_response: dict[str, Any],
        model: str,
    ) -> ChatCompletionResponse:
        candidates = raw_response.get("candidates", [])

        choices: list[Choice] = []
        for i, candidate in enumerate(candidates):
            content = candidate.get("content", {})
            parts = content.get("parts", [])

            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []

            for part in parts:
                if "text" in part:
                    text_parts.append(part["text"])
                elif "functionCall" in part:
                    fc = part["functionCall"]
                    tool_calls.append({
                        "id": f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": fc.get("name", ""),
                            "arguments": json.dumps(fc.get("args", {})),
                        },
                    })

            message = ChatMessage(
                role="assistant",
                content="\n".join(text_parts) if text_parts else None,
                tool_calls=tool_calls if tool_calls else None,
            )

            finish_reason = self._map_finish_reason(candidate.get("finishReason"))

            choices.append(Choice(index=i, message=message, finish_reason=finish_reason))

        # Usage metadata
        usage_meta = raw_response.get("usageMetadata", {})
        prompt_tokens = usage_meta.get("promptTokenCount", 0)
        completion_tokens = usage_meta.get("candidatesTokenCount", 0)

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
            created=int(time.time()),
            model=model,
            choices=choices,
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    @staticmethod
    def _map_finish_reason(reason: str | None) -> str:
        mapping = {
            "STOP": "stop",
            "MAX_TOKENS": "length",
            "SAFETY": "content_filter",
            "RECITATION": "content_filter",
            "OTHER": "stop",
        }
        return mapping.get(reason or "", "stop")

    # Non-Streaming

    async def send(
        self,
        request: ChatCompletionRequest,
        deployment: ModelDeployment,
    ) -> ChatCompletionResponse:
        url, headers, body = self.transform_request(request, deployment)

        try:
            response = await self.client.post(url, headers=headers, json=body, timeout=120.0)
        except httpx.TimeoutException as e:
            raise ProviderError(
                f"Gemini request timed out: {e}",
                details={"provider": "google", "deployment": deployment.name},
            ) from e
        except httpx.ConnectError as e:
            raise ProviderError(
                f"Failed to connect to Gemini: {e}",
                details={"provider": "google", "deployment": deployment.name},
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
        Stream from Gemini's SSE endpoint.

        Gemini streams complete candidate objects per event, each containing
        incremental content parts and running usageMetadata.
        """
        url, headers, body = self.transform_request(request, deployment)

        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())
        is_first = True
        prompt_tokens = 0
        completion_tokens = 0

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

                    candidates = event.get("candidates", [])
                    if not candidates:
                        continue

                    candidate = candidates[0]
                    content = candidate.get("content", {})
                    parts = content.get("parts", [])

                    # Track usage
                    usage_meta = event.get("usageMetadata", {})
                    if usage_meta:
                        prompt_tokens = usage_meta.get("promptTokenCount", prompt_tokens)
                        completion_tokens = usage_meta.get(
                            "candidatesTokenCount", completion_tokens
                        )

                    # Build delta
                    text = ""
                    for part in parts:
                        if "text" in part:
                            text += part["text"]

                    delta: dict[str, Any] = {}
                    if is_first:
                        delta["role"] = "assistant"
                        is_first = False
                    if text:
                        delta["content"] = text

                    finish_reason_raw = candidate.get("finishReason")
                    finish_reason = (
                        self._map_finish_reason(finish_reason_raw)
                        if finish_reason_raw and finish_reason_raw != "FINISH_REASON_UNSPECIFIED"
                        else None
                    )

                    # Include usage in the chunk if we have a finish reason
                    usage = None
                    if finish_reason:
                        usage = Usage(
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            total_tokens=prompt_tokens + completion_tokens,
                        )

                    yield ChatCompletionChunk(
                        id=chunk_id,
                        created=created,
                        model=request.model,
                        choices=[
                            StreamChoice(
                                index=0,
                                delta=delta,
                                finish_reason=finish_reason,
                            )
                        ],
                        usage=usage,
                    )

        except httpx.TimeoutException as e:
            raise ProviderError(
                f"Gemini stream timed out: {e}",
                details={"provider": "google", "deployment": deployment.name},
            ) from e