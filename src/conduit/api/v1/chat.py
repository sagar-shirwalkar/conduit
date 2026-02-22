"""
POST /v1/chat/completions — Core proxy endpoint.

Supports both streaming (SSE) and non-streaming responses.
Full pipeline: Auth -> Rate Limit -> Route -> Provider -> Cost -> Log
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import ORJSONResponse, StreamingResponse

from conduit.api.deps import AuthenticatedKey, DBSession
from conduit.schemas.completion import ChatCompletionRequest, ChatCompletionResponse
from conduit.services.completion import CompletionService, get_completion_service

logger = structlog.stdlib.get_logger()

router = APIRouter()


@router.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    summary="Create chat completion",
    description=(
        "OpenAI-compatible chat completion endpoint. "
        "Routes to configured providers. Supports streaming via SSE."
    ),
)
async def create_chat_completion(
    body: ChatCompletionRequest,
    request: Request,
    api_key: AuthenticatedKey,
    db: DBSession,
    service: Annotated[CompletionService, Depends(get_completion_service)],
) -> ORJSONResponse | StreamingResponse:
    request_id = getattr(request.state, "request_id", "unknown")

    await logger.ainfo(
        "chat.completion.request",
        model=body.model,
        messages_count=len(body.messages),
        stream=body.stream,
        api_key_prefix=api_key.key_prefix,
    )

    if body.stream:
        # Streaming SSE
        sse_generator, headers = await service.create_streaming_completion(
            request=body,
            api_key=api_key,
            request_id=request_id,
            db=db,
        )

        return StreamingResponse(
            content=sse_generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
                "x-conduit-request-id": request_id,
                **headers,
            },
        )

    else:
        # Non-Streaming
        result = await service.create_completion(
            request=body,
            api_key=api_key,
            request_id=request_id,
            db=db,
        )

        response = ORJSONResponse(content=result.response.model_dump())

        response.headers["x-conduit-cache"] = "HIT" if result.cached else "MISS"
        response.headers["x-conduit-cost-usd"] = str(result.cost_usd)
        response.headers["x-conduit-provider"] = result.provider
        response.headers["x-conduit-request-id"] = request_id

        # Rate limit headers
        for key, value in result.rate_limit_headers.items():
            response.headers[key] = value

        return response