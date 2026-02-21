"""Token counting utilities."""

from __future__ import annotations

from functools import lru_cache

import tiktoken


@lru_cache(maxsize=16)
def _get_encoding(model: str) -> tiktoken.Encoding:
    """Get tiktoken encoding for a model, with fallback."""
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count tokens in a text string."""
    enc = _get_encoding(model)
    return len(enc.encode(text))


def count_message_tokens(messages: list[dict], model: str = "gpt-4o") -> int:
    """
    Count tokens in a list of chat messages.
    
    Uses OpenAI's token counting conventions:
    - 4 tokens per message overhead
    - 2 tokens for reply priming
    """
    enc = _get_encoding(model)
    tokens = 0
    for message in messages:
        tokens += 4  # message overhead
        for key, value in message.items():
            if isinstance(value, str):
                tokens += len(enc.encode(value))
            elif isinstance(value, list):
                # Handle content arrays (vision, etc.)
                for item in value:
                    if isinstance(item, dict) and "text" in item:
                        tokens += len(enc.encode(item["text"]))
    tokens += 2  # reply priming
    return tokens