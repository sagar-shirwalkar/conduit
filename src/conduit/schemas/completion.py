"""
Completion service — full request lifecycle with cache + guardrails.

Non-streaming: Auth → Rate Limit → Guardrails(pre) → Cache → Route → Provider → Guardrails(post) → Cost → Cache Store → Log
Streaming:     Auth → Rate Limit → Guardrails(pre) → Route → Provider → [stream] → Cost → Log
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, AsyncIterator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.common.errors import NoHealthyDeploymentError, ProviderError
from conduit.common.streaming import SSE_DONE, StreamAccumulator, format_sse
from conduit.config import get_settings
from conduit.core.auth.api_key import check_budget, check_model_access
from conduit.core.auth.rate_limiter import RateLimitResult, get_rate_limiter
from conduit.core.cache.manager import CacheManager
from conduit.core.cost.calculator import calculate_cost
from conduit.core.guardrails.engine import GuardrailEngine
from conduit.core.router.engine import RouterEngine
from conduit.models.api_key import APIKey
from conduit.models.deployment import ModelDeployment
from conduit.models.request_log import RequestLog
from conduit.providers.registry import get_adapter
from conduit.schemas.completion import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    Usage,
)

logger = structlog.stdlib.get_logger()


@dataclass
class CompletionResult:
    response: ChatCompletionResponse
    cost_usd: Decimal
    provider: str
    deployment_name: str
    latency_ms: int
    cached: bool
    rate_limit_headers: dict[str, str] = field(default_factory=dict)
    guardrail_warnings: list[str] = field(default_factory=list)


class CompletionService:
    def __init__(self, router: RouterEngine) -> None:
        self.router = router

    # Rate Limiting

    async def _check_rate_limits(
        self, api_key: APIKey
    ) -> tuple[dict[str, str], RateLimitResult | None]:
        headers: dict[str, str] = {}
        rpm_result: RateLimitResult | None = None

        if api_key.key_hash == "master":
            return headers, rpm_result

        rate_limiter = get_rate_limiter()

        if api_key.rate_limit_rpm:
            rpm_result = await rate_limiter.check_or_raise(
                identifier=f"rpm:key:{api_key.id}",
                limit=api_key.rate_limit_rpm,
                window_seconds=60,
            )
            headers.update(rpm_result.to_headers("requests"))

        return headers, rpm_result

    async def _update_token_usage(self, api_key: APIKey, total_tokens: int) -> None:
        if api_key.key_hash == "master" or not api_key.rate_limit_tpm:
            return
        rate_limiter = get_rate_limiter()
        await rate_limiter.update_token_usage(
            identifier=f"tpm:key:{api_key.id}",
            token_count=total_tokens,
            limit=api_key.rate_limit_tpm,
            window_seconds=60,
        )

    # Non-Streaming Completion

    async def create_completion(
        self,
        request: ChatCompletionRequest,
        api_key: APIKey,
        request_id: str,
        db: AsyncSession,
    ) -> CompletionResult:
        start = time.perf_counter()
        settings = get_settings()

        # Step 1: Access control
        check_model_access(api_key, request.model)
        check_budget(api_key)

        # Step 2: Rate limiting
        rl_headers, _ = await self._check_rate_limits(api_key)

        # Step 3: Pre-request guardrails
        guardrail_warnings: list[str] = []
        messages_dicts = [m.model_dump(exclude_none=True) for m in request.messages]

        guardrail_engine = GuardrailEngine(db)
        if guardrail_engine.enabled:
            gr_result = await guardrail_engine.run_pre_request(messages_dicts, request.model)
            guardrail_warnings = [v.details for v in gr_result.violations]
            if gr_result.messages_modified and gr_result.modified_messages:
                messages_dicts = gr_result.modified_messages
                # Rebuild the request messages from redacted versions
                request = request.model_copy(
                    update={
                        "messages": [
                            ChatMessage(**m) for m in messages_dicts
                        ]
                    }
                )

        # Step 4: Cache lookup
        cache_manager = CacheManager(db)
        if cache_manager.enabled and not request.stream:
            cache_result = await cache_manager.lookup(messages_dicts, request.model)
            if cache_result.hit and cache_result.response_payload:
                latency_ms = int((time.perf_counter() - start) * 1000)
                cached_response = ChatCompletionResponse(**cache_result.response_payload)

                # Log cached hit
                log_entry = RequestLog(
                    request_id=request_id,
                    api_key_id=api_key.id if api_key.key_hash != "master" else None,
                    model=request.model,
                    provider="cache",
                    prompt_tokens=cached_response.usage.prompt_tokens,
                    completion_tokens=cached_response.usage.completion_tokens,
                    cost_usd=Decimal("0"),
                    latency_ms=latency_ms,
                    status_code=200,
                    cached=True,
                )
                db.add(log_entry)

                await logger.ainfo(
                    "chat.completion.cache_hit",
                    model=request.model,
                    source=cache_result.source,
                    latency_ms=latency_ms,
                )

                return CompletionResult(
                    response=cached_response,
                    cost_usd=Decimal("0"),
                    provider="cache",
                    deployment_name="cache",
                    latency_ms=latency_ms,
                    cached=True,
                    rate_limit_headers=rl_headers,
                    guardrail_warnings=guardrail_warnings,
                )

        # Step 5: Route (get fallback chain)
        deployment_chain = await self.router.route(request.model, db)

        # Step 6: Try deployments with fallback
        response: ChatCompletionResponse | None = None
        used_deployment: ModelDeployment | None = None
        last_error: Exception | None = None

        for deployment in deployment_chain:
            adapter = get_adapter(deployment.provider.value)
            try:
                response = await adapter.send(request, deployment)
                await self.router.record_success(deployment, db)
                used_deployment = deployment
                break
            except ProviderError as e:
                last_error = e
                await self.router.record_failure(deployment, db)
                await logger.awarning(
                    "chat.completion.fallback",
                    failed_deployment=deployment.name,
                    error=str(e),
                )
                continue

        if response is None or used_deployment is None:
            if last_error:
                raise last_error
            raise NoHealthyDeploymentError(f"All deployments failed for model '{request.model}'")

        latency_ms = int((time.perf_counter() - start) * 1000)

        # Step 7: Post-response guardrails
        if guardrail_engine.enabled:
            response_text = ""
            if response.choices:
                response_text = response.choices[0].message.content or ""
            post_result = await guardrail_engine.run_post_response(response_text, request.model)
            guardrail_warnings.extend(v.details for v in post_result.violations)

        # Step 8: Cost calculation
        cost = calculate_cost(
            model=request.model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )

        # Step 9: Update spend
        if api_key.key_hash != "master":
            api_key.spend_usd = api_key.spend_usd + cost
            await db.flush()

        await self._update_token_usage(api_key, response.usage.total_tokens)

        # Step 10: Store in cache
        if cache_manager.enabled:
            await cache_manager.store(
                messages=messages_dicts,
                model=request.model,
                response_payload=response.model_dump(),
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
            )

        # Step 11: Log request
        log_entry = RequestLog(
            request_id=request_id,
            api_key_id=api_key.id if api_key.key_hash != "master" else None,
            deployment_id=used_deployment.id,
            model=request.model,
            provider=used_deployment.provider.value,
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
            provider=used_deployment.provider.value,
            deployment=used_deployment.name,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            cost_usd=str(cost),
            latency_ms=latency_ms,
            cached=False,
        )

        return CompletionResult(
            response=response,
            cost_usd=cost,
            provider=used_deployment.provider.value,
            deployment_name=used_deployment.name,
            latency_ms=latency_ms,
            cached=False,
            rate_limit_headers=rl_headers,
            guardrail_warnings=guardrail_warnings,
        )

    # ── Streaming Completion ────────────────────────────

    async def create_streaming_completion(
        self,
        request: ChatCompletionRequest,
        api_key: APIKey,
        request_id: str,
        db: AsyncSession,
    ) -> tuple[AsyncIterator[str], dict[str, str]]:
        check_model_access(api_key, request.model)
        check_budget(api_key)

        rl_headers, _ = await self._check_rate_limits(api_key)

        # Pre-request guardrails
        messages_dicts = [m.model_dump(exclude_none=True) for m in request.messages]
        guardrail_engine = GuardrailEngine(db)
        if guardrail_engine.enabled:
            gr_result = await guardrail_engine.run_pre_request(messages_dicts, request.model)
            if gr_result.messages_modified and gr_result.modified_messages:
                request = request.model_copy(
                    update={
                        "messages": [ChatMessage(**m) for m in gr_result.modified_messages]
                    }
                )

        deployment_chain = await self.router.route(request.model, db)

        sse_gen = self._stream_with_fallback(
            request=request,
            api_key=api_key,
            request_id=request_id,
            deployment_chain=deployment_chain,
            db=db,
        )

        return sse_gen, rl_headers

    async def _stream_with_fallback(
        self,
        request: ChatCompletionRequest,
        api_key: APIKey,
        request_id: str,
        deployment_chain: list[ModelDeployment],
        db: AsyncSession,
    ) -> AsyncIterator[str]:
        start = time.perf_counter()
        accumulator = StreamAccumulator()
        used_deployment: ModelDeployment | None = None
        last_error: Exception | None = None

        for deployment in deployment_chain:
            adapter = get_adapter(deployment.provider.value)
            try:
                chunk_iter = adapter.stream(request, deployment)
                async for sse_line in self._format_and_accumulate(chunk_iter, accumulator):
                    yield sse_line
                await self.router.record_success(deployment, db)
                used_deployment = deployment
                break
            except ProviderError as e:
                if accumulator.chunks_sent == 0:
                    last_error = e
                    await self.router.record_failure(deployment, db)
                    continue
                else:
                    yield format_sse({"error": {"message": f"Stream interrupted: {e.message}", "type": "stream_error"}})
                    yield SSE_DONE
                    await self.router.record_failure(deployment, db)
                    used_deployment = deployment
                    break

        if used_deployment is None and accumulator.chunks_sent == 0:
            error_msg = str(last_error) if last_error else "All deployments failed"
            yield format_sse({"error": {"message": error_msg, "type": "no_healthy_deployment"}})
            yield SSE_DONE
            return

        # Post-stream side effects
        latency_ms = int((time.perf_counter() - start) * 1000)

        if accumulator.completion_tokens == 0 and accumulator.assembled_content:
            from conduit.common.tokens import count_tokens
            accumulator.completion_tokens = count_tokens(accumulator.assembled_content, request.model)
        if accumulator.prompt_tokens == 0:
            from conduit.common.tokens import count_message_tokens
            accumulator.prompt_tokens = count_message_tokens(
                [m.model_dump(exclude_none=True) for m in request.messages], request.model
            )

        cost = calculate_cost(request.model, accumulator.prompt_tokens, accumulator.completion_tokens)

        if api_key.key_hash != "master":
            api_key.spend_usd = api_key.spend_usd + cost
            await db.flush()

        await self._update_token_usage(api_key, accumulator.total_tokens)

        log_entry = RequestLog(
            request_id=request_id,
            api_key_id=api_key.id if api_key.key_hash != "master" else None,
            deployment_id=used_deployment.id if used_deployment else None,
            model=request.model,
            provider=used_deployment.provider.value if used_deployment else "unknown",
            prompt_tokens=accumulator.prompt_tokens,
            completion_tokens=accumulator.completion_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            status_code=200,
            cached=False,
        )
        db.add(log_entry)

    async def _format_and_accumulate(
        self, chunks: AsyncIterator, accumulator: StreamAccumulator
    ) -> AsyncIterator[str]:
        async for chunk in chunks:
            choices = chunk.choices if hasattr(chunk, "choices") else []
            if choices:
                delta = choices[0].delta if hasattr(choices[0], "delta") else {}
                content = delta.get("content") if isinstance(delta, dict) else None
                accumulator.record_chunk(content)
                fr = choices[0].finish_reason if hasattr(choices[0], "finish_reason") else None
                if fr:
                    accumulator.finish_reason = fr

            usage = chunk.usage if hasattr(chunk, "usage") else None
            if usage:
                accumulator.prompt_tokens = usage.prompt_tokens
                accumulator.completion_tokens = usage.completion_tokens

            sse_dict = chunk.to_sse_dict() if hasattr(chunk, "to_sse_dict") else chunk
            yield format_sse(sse_dict)

        yield SSE_DONE


def get_completion_service() -> CompletionService:
    return CompletionService(router=RouterEngine())