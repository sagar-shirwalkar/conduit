"""
Server-Sent Events (SSE) streaming utilities.

Handles the full streaming lifecycle:
  1. Format provider chunks as SSE lines
  2. Accumulate token usage across chunks
  3. Fire post-stream side effects (logging, cost, spend)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, AsyncIterator

import structlog

logger = structlog.stdlib.get_logger()


@dataclass
class StreamAccumulator:
    """Accumulates metadata across streamed chunks for post-stream processing."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str | None = None
    first_token_at: float | None = None
    chunks_sent: int = 0
    full_content: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def record_chunk(self, content: str | None = None) -> None:
        self.chunks_sent += 1
        if self.first_token_at is None and content:
            self.first_token_at = time.perf_counter()
        if content:
            self.full_content.append(content)

    @property
    def assembled_content(self) -> str:
        return "".join(self.full_content)


def format_sse(data: dict[str, Any] | str) -> str:
    """Format a single SSE event line."""
    if isinstance(data, dict):
        payload = json.dumps(data, separators=(",", ":"))
    else:
        payload = data
    return f"data: {payload}\n\n"


SSE_DONE = "data: [DONE]\n\n"


async def stream_sse_response(
    chunks: AsyncIterator[dict[str, Any]],
    accumulator: StreamAccumulator,
) -> AsyncIterator[str]:
    """
    Consume provider chunks and yield SSE-formatted strings.

    The accumulator is mutated in-place so the caller can inspect
    token counts / content after the stream completes.
    """
    try:
        async for chunk in chunks:
            # Extract content from the delta for accumulation
            choices = chunk.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content")
                accumulator.record_chunk(content)

                finish = choices[0].get("finish_reason")
                if finish:
                    accumulator.finish_reason = finish

            # Extract usage if present (some providers send in final chunk)
            usage = chunk.get("usage")
            if usage:
                accumulator.prompt_tokens = usage.get("prompt_tokens", accumulator.prompt_tokens)
                accumulator.completion_tokens = usage.get(
                    "completion_tokens", accumulator.completion_tokens
                )

            yield format_sse(chunk)

    except Exception as exc:
        await logger.aerror("stream.error", error=str(exc))
        error_chunk = {
            "error": {
                "message": f"Stream interrupted: {exc}",
                "type": "stream_error",
            }
        }
        yield format_sse(error_chunk)

    finally:
        yield SSE_DONE