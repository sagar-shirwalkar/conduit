"""
Local embedding model for semantic cache.

Uses fastembed (ONNX Runtime) for lightweight, dependency-free
vector generation. No PyTorch/GPU needed.

Model: BAAI/bge-small-en-v1.5 (384 dimensions, 45MB)
"""

from __future__ import annotations

import structlog
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastembed import TextEmbedding

logger = structlog.stdlib.get_logger()

_model: TextEmbedding | None = None


def get_embedding_model(model_name: str = "BAAI/bge-small-en-v1.5") -> TextEmbedding:
    """
    Get or lazily initialize the embedding model.

    The model is loaded once and cached for the process lifetime.
    First call downloads the model if not cached locally.
    """
    global _model  # noqa: PLW0603
    if _model is not None:
        return _model

    from fastembed import TextEmbedding

    logger.info("embedding.loading", model=model_name)
    _model = TextEmbedding(model_name=model_name)
    logger.info("embedding.loaded", model=model_name)
    return _model


def embed_text(text: str, model_name: str = "BAAI/bge-small-en-v1.5") -> list[float]:
    """
    Generate embedding vector for a single text string.

    Returns:
        List of floats (384 dimensions for bge-small-en-v1.5)
    """
    model = get_embedding_model(model_name)
    embeddings = list(model.embed([text]))
    return embeddings[0].tolist()


def embed_texts(texts: list[str], model_name: str = "BAAI/bge-small-en-v1.5") -> list[list[float]]:
    """Generate embeddings for multiple texts (batched for efficiency)"""
    model = get_embedding_model(model_name)
    return [e.tolist() for e in model.embed(texts)]


def normalize_prompt_for_embedding(messages: list[dict]) -> str:
    """
    Flatten a chat message list into a single string for embedding.

    Strategy: Concatenate all message contents, preserving role context
    but focusing on semantic meaning. Skip system messages for cache
    matching - they're typically static per app
    """
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            continue  # System prompts are stable — don't vary cache
        if isinstance(content, str):
            parts.append(f"{role}: {content}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    parts.append(f"{role}: {block['text']}")
    return "\n".join(parts)