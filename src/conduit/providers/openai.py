"""OpenAI provider adapter (also works for Azure OpenAI)."""

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


class OpenAIAdapter(ProviderAdapter):
    provider_name = "openai"

    def transform_request(
        self,
        request: ChatCompletionRequest,
        deployment: ModelDeployment,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        url = f"{deployment.api_base}/chat/completions"

        headers = {
            "Authorization": f"Bearer {decrypt_value(deployment.api_key_encrypted)}",
            "Content-Type": "application/json",
        }

        # Build body — only include non-None fields
        body: dict[str, Any] = {
            "model": deployment.model_name,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
        }

        # Optional parameters
        optional_fields = {
            "temperature": request.temperature,
            "top_p": request.top_p,
            "n": request.n,
            "stream": request.stream,
            "stop": request.stop,
            "max_tokens": request.max_tokens,
            "presence_penalty": request.presence_penalty,
            "frequency_penalty": request.frequency_penalty,
            "tools": request.tools,
            "tool_choice": request.tool_choice,
            "response_format": request.response_format,
            "seed": request.seed,
            "user": request.user,
        }

        for key, value in optional_fields.items():
            if value is not None:
                body[key] = value

        return url, headers, body

    def transform_response(
        self,
        raw_response: dict[str, Any],
        model: str,
    ) -> ChatCompletionResponse:
        """OpenAI response is already in our target format — minimal transform."""
        choices = []
        for raw_choice in raw_response.get("choices", []):
            msg = raw_choice.get("message", {})
            choices.append(
                Choice(
                    index=raw_choice.get("index", 0),
                    message=ChatMessage(
                        role=msg.get("role", "assistant"),
                        content=msg.get("content"),
                        tool_calls=msg.get("tool_calls"),
                    ),
                    finish_reason=raw_choice.get("finish_reason"),
                )
            )

        raw_usage = raw_response.get("usage", {})

        return ChatCompletionResponse(
            id=raw_response.get("id", f"chatcmpl-{uuid.uuid4().hex[:24]}"),
            created=raw_response.get("created", int(time.time())),
            model=model,
            choices=choices,
            usage=Usage(
                prompt_tokens=raw_usage.get("prompt_tokens", 0),
                completion_tokens=raw_usage.get("completion_tokens", 0),
                total_tokens=raw_usage.get("total_tokens", 0),
            ),
        )

    async def send(
        self,
        request: ChatCompletionRequest,
        deployment: ModelDeployment,
    ) -> ChatCompletionResponse:
        """Send a non-streaming request to OpenAI."""
        url, headers, body = self.transform_request(request, deployment)

        try:
            response = await self.client.post(
                url,
                headers=headers,
                json=body,
                timeout=120.0,
            )
        except httpx.TimeoutException as e:
            raise ProviderError(
                f"OpenAI request timed out: {e}",
                details={"provider": "openai", "deployment": deployment.name},
            ) from e
        except httpx.ConnectError as e:
            raise ProviderError(
                f"Failed to connect to OpenAI: {e}",
                details={"provider": "openai", "deployment": deployment.name},
            ) from e

        if response.status_code != 200:
            error_body = response.text
            await logger.aerror(
                "provider.openai.error",
                status_code=response.status_code,
                body=error_body[:500],
                deployment=deployment.name,
            )
            raise ProviderError(
                f"OpenAI returned {response.status_code}: {error_body[:200]}",
                details={
                    "provider": "openai",
                    "status_code": response.status_code,
                    "deployment": deployment.name,
                },
            )

        raw = response.json()
        return self.transform_response(raw, request.model)

    async def stream(
        self,
        request: ChatCompletionRequest,
        deployment: ModelDeployment,
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Stream chunks from OpenAI (Phase 2)."""
        url, headers, body = self.transform_request(request, deployment)
        body["stream"] = True

        async with self.client.stream("POST", url, headers=headers, json=body, timeout=120.0) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                    yield ChatCompletionChunk(
                        id=event.get("id", ""),
                        created=event.get("created", int(time.time())),
                        model=request.model,
                        choices=[
                            StreamChoice(
                                index=c.get("index", 0),
                                delta=c.get("delta", {}),
                                finish_reason=c.get("finish_reason"),
                            )
                            for c in event.get("choices", [])
                        ],
                    )
                except json.JSONDecodeError:
                    continue