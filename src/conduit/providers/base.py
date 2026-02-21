"""Abstract base class for LLM provider adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

import httpx

from conduit.models.deployment import ModelDeployment
from conduit.schemas.completion import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
)


class ProviderAdapter(ABC):
    """
    Base class for all LLM provider adapters.

    Each adapter handles:
      1. Transforming Conduit's OpenAI-compatible request → provider's native format
      2. Making the HTTP call
      3. Transforming the provider's response → OpenAI-compatible format
      4. Mapping provider errors → Conduit's error taxonomy
    """

    provider_name: str

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self.client = http_client

    @abstractmethod
    def transform_request(
        self,
        request: ChatCompletionRequest,
        deployment: ModelDeployment,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        """
        Transform a Conduit request into a provider-native request.

        Returns:
            (url, headers, body)
        """
        ...

    @abstractmethod
    def transform_response(
        self,
        raw_response: dict[str, Any],
        model: str,
    ) -> ChatCompletionResponse:
        """Transform a provider response into an OpenAI-compatible response."""
        ...

    @abstractmethod
    async def stream(
        self,
        request: ChatCompletionRequest,
        deployment: ModelDeployment,
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Yield OpenAI-compatible SSE chunks from the provider's stream."""
        ...  # pragma: no cover
        # Make this a valid async generator
        if False:
            yield  # type: ignore[misc]

    def extract_usage(self, raw_response: dict[str, Any]) -> tuple[int, int]:
        """Extract (prompt_tokens, completion_tokens) from provider response."""
        usage = raw_response.get("usage", {})
        return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)