"""Abstract base class for LLM provider adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

import httpx
import structlog

from conduit.common.errors import ProviderError
from conduit.models.deployment import ModelDeployment
from conduit.schemas.completion import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
)

logger = structlog.stdlib.get_logger()


class ProviderAdapter(ABC):
    """
    Base class for all LLM provider adapters.

    Subclasses must implement:
      - transform_request() : convert to provider's native format
      - transform_response() : convert back to OpenAI format
      - send() : non-streaming completion
      - stream() : async iterator of SSE chunks
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
        """Returns (url, headers, body) for the provider's API."""
        ...

    @abstractmethod
    def transform_response(
        self,
        raw_response: dict[str, Any],
        model: str,
    ) -> ChatCompletionResponse:
        """Transform provider response → OpenAI-compatible response."""
        ...

    @abstractmethod
    async def send(
        self,
        request: ChatCompletionRequest,
        deployment: ModelDeployment,
    ) -> ChatCompletionResponse:
        """Send a non-streaming completion request."""
        ...

    @abstractmethod
    async def stream(
        self,
        request: ChatCompletionRequest,
        deployment: ModelDeployment,
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Yield OpenAI-compatible SSE chunks."""
        ...
        if False:
            yield  # type: ignore[misc]  # pragma: no cover

    def extract_usage(self, raw_response: dict[str, Any]) -> tuple[int, int]:
        """Extract (prompt_tokens, completion_tokens) from provider response."""
        usage = raw_response.get("usage", {})
        return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)

    async def _handle_error_response(
        self,
        response: httpx.Response,
        deployment: ModelDeployment,
    ) -> None:
        """Shared error handling for non-2xx responses."""
        error_body = response.text
        await logger.aerror(
            f"provider.{self.provider_name}.error",
            status_code=response.status_code,
            body=error_body[:500],
            deployment=deployment.name,
        )

        # Map provider status codes to appropriate Conduit errors
        if response.status_code == 401:
            raise ProviderError(
                f"{self.provider_name} authentication failed for deployment '{deployment.name}'",
                details={"provider": self.provider_name, "status_code": 401},
            )
        if response.status_code == 429:
            raise ProviderError(
                f"{self.provider_name} rate limit exceeded on deployment '{deployment.name}'",
                details={"provider": self.provider_name, "status_code": 429, "retry": True},
            )

        raise ProviderError(
            f"{self.provider_name} returned {response.status_code}: {error_body[:200]}",
            details={
                "provider": self.provider_name,
                "status_code": response.status_code,
                "deployment": deployment.name,
            },
        )