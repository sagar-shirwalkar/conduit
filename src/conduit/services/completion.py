"""
Completion service — orchestrates the full request lifecycle:

  Auth Check → Budget Check → Model Access → Route → Provider Call → Cost Calc → Log
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from decimal import Decimal

import structlog
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.common.errors import ProviderError
from conduit.core.auth.api_key import check_budget, check_model_access
from conduit.core.cost.calculator import calculate_cost
from conduit.core.router.engine import RouterEngine
from conduit.models.api_key import APIKey
from conduit.models.request_log import RequestLog
from conduit.providers.registry import get_adapter
from conduit.schemas.completion import ChatCompletionRequest, ChatCompletionResponse

logger = structlog.stdlib.get_logger()


@dataclass
class CompletionResult:
    """Result of a completion request, including metadata."""

    response: ChatCompletionResponse
    cost_usd: Decimal
    provider: str
    deployment_name: str
    latency_ms: int
    cached: bool


class CompletionService:
    """Orchestrates the full chat completion lifecycle."""

    def __init__(self, router: RouterEngine) -> None:
        self.router = router

    async def create_completion(
        self,
        request: ChatCompletionRequest,
        api_key: APIKey,
        request_id: str,
        db: AsyncSession,
    ) -> CompletionResult:
        start = time.perf_counter()

        # Step 1: Access checks
        check_model_access(api_key, request.model)
        check_budget(api_key)

        # Step 2: Route to deployment
        deployment = await self.router.route(request.model, db)

        # Step 3: Call provider
        adapter = get_adapter(deployment.provider.value)

        try:
            response = await adapter.send(request, deployment)
            await self.router.mark_success(deployment, db)
        except ProviderError:
            await self.router.mark_failure(deployment, db)
            raise

        latency_ms = int((time.perf_counter() - start) * 1000)

        # Step 4: Calculate cost
        cost = calculate_cost(
            model=request.model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )

        # Step 5: Update spend
        if api_key.key_hash != "master":
            api_key.spend_usd = api_key.spend_usd + cost
            await db.flush()

        # Step 6: Log request
        log_entry = RequestLog(
            request_id=request_id,
            api_key_id=api_key.id if api_key.key_hash != "master" else None,
            deployment_id=deployment.id,
            model=request.model,
            provider=deployment.provider.value,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            status_code=200,
            cached=False,
        )
        db.add(log_entry)

        await logger.ainfo(
            "chat.completion.success",
            model=request.model,
            provider=deployment.provider.value,
            deployment=deployment.name,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            cost_usd=str(cost),
            latency_ms=latency_ms,
        )

        return CompletionResult(
            response=response,
            cost_usd=cost,
            provider=deployment.provider.value,
            deployment_name=deployment.name,
            latency_ms=latency_ms,
            cached=False,
        )


# FastAPI Dependency

def get_completion_service() -> CompletionService:
    return CompletionService(router=RouterEngine())