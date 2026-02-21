"""
POST /v1/chat/completions — Core proxy endpoint.

Accepts OpenAI-compatible requests, routes them through:
  Auth → Rate Limit → Guardrails → Cache → Router → Provider → Log
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import ORJSONResponse

from conduit.api.deps import AuthenticatedKey, DBSession
from conduit.schemas.completion import ChatCompletionRequest, ChatCompletionResponse
from conduit.services.completion import CompletionService, get_completion_service

logger = structlog.stdlib.get_logger()

router = APIRouter()


@router.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    response_class=ORJSONResponse,
    summary="Create chat completion",
    description="OpenAI-compatible chat completion endpoint. Routes to configured providers.",
)
async def create_chat_completion(
    body: ChatCompletionRequest,
    request: Request,
    api_key: AuthenticatedKey,
    db: DBSession,
    service: Annotated[CompletionService, Depends(get_completion_service)],
) -> ORJSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")

    await logger.ainfo(
        "chat.completion.request",
        model=body.model,
        messages_count=len(body.messages),
        stream=body.stream,
        api_key_prefix=api_key.key_prefix,
    )

    # TODO Phase 2: streaming support
    if body.stream:
        # For now, return an error for streaming requests
        return ORJSONResponse(
            status_code=501,
            content={
                "error": {
                    "message": "Streaming is not yet supported. Coming in Phase 2.",
                    "type": "not_implemented",
                    "code": 501,
                }
            },
        )

    result = await service.create_completion(
        request=body,
        api_key=api_key,
        request_id=request_id,
        db=db,
    )

    response = ORJSONResponse(content=result.response.model_dump())

    # Conduit metadata headers
    response.headers["x-conduit-cache"] = "HIT" if result.cached else "MISS"
    response.headers["x-conduit-cost-usd"] = str(result.cost_usd)
    response.headers["x-conduit-provider"] = result.provider
    response.headers["x-conduit-request-id"] = request_id

    return response