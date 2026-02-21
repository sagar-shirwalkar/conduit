"""
In-process event bus for decoupled side effects.

Used for non-blocking operations like logging, analytics,
and spend updates after a request completes.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Coroutine
from uuid import UUID

import structlog

logger = structlog.stdlib.get_logger()

# Type alias for async event handlers
EventHandler = Callable[..., Coroutine[Any, Any, None]]


@dataclass
class RequestCompletedEvent:
    """Emitted after every completed LLM request."""

    request_id: str
    api_key_id: UUID
    deployment_id: UUID
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    latency_ms: int
    status_code: int
    cached: bool
    created_at: datetime = field(default_factory=datetime.utcnow)


class EventBus:
    """Simple async pub/sub event bus."""

    def __init__(self) -> None:
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: Any) -> None:
        """Publish an event — handlers run concurrently, errors are logged not raised."""
        handlers = self._handlers.get(type(event), [])
        if not handlers:
            return

        results = await asyncio.gather(
            *(h(event) for h in handlers),
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                await logger.aerror(
                    "event_bus.handler_error",
                    event_type=type(event).__name__,
                    handler=handlers[i].__name__,
                    error=str(result),
                )


# Global event bus instance
event_bus = EventBus()