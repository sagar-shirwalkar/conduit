"""Request/response logging middleware."""

from __future__ import annotations

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.stdlib.get_logger()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = int((time.perf_counter() - start) * 1000)

        # Skip health check noise
        if request.url.path in ("/admin/v1/health/live", "/admin/v1/health/ready"):
            return response

        await logger.ainfo(
            "http.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
            client=request.client.host if request.client else None,
        )

        response.headers["x-conduit-latency-ms"] = str(duration_ms)
        return response