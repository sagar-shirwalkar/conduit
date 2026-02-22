"""Provider adapter registry — maps provider names to adapter classes."""

from __future__ import annotations

import httpx

from conduit.providers.anthropic import AnthropicAdapter
from conduit.providers.base import ProviderAdapter
from conduit.providers.google import GoogleAdapter
from conduit.providers.openai import OpenAIAdapter

# Registry: provider name → adapter class
_ADAPTERS: dict[str, type[ProviderAdapter]] = {
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "google": GoogleAdapter,
    # Phase 4:
    # "mistral": MistralAdapter,
    # "cohere": CohereAdapter,
    # "bedrock": BedrockAdapter,
    # "ollama": OllamaAdapter,
    # "deepseek": DeepSeekAdapter,
}

_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Get or create the shared async HTTP client."""
    global _http_client  # noqa: PLW0603
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=10.0),
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
            http2=True,
            follow_redirects=True,
        )
    return _http_client


async def close_http_client() -> None:
    """Close the shared HTTP client (called on app shutdown)."""
    global _http_client  # noqa: PLW0603
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


def get_adapter(provider: str) -> ProviderAdapter:
    """Get an adapter instance for the given provider."""
    adapter_cls = _ADAPTERS.get(provider)
    if adapter_cls is None:
        supported = ", ".join(sorted(_ADAPTERS.keys()))
        raise ValueError(f"Unsupported provider: '{provider}'. Supported: {supported}")
    return adapter_cls(get_http_client())


def list_supported_providers() -> list[str]:
    """Return all registered provider names."""
    return sorted(_ADAPTERS.keys())