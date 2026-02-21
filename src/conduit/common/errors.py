"""
Unified error handling.

All Conduit errors map to OpenAI-compatible error responses so that
existing SDKs (openai-python, etc.) can parse them.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse

logger = structlog.stdlib.get_logger()


class ConduitError(Exception):
    """Base exception for all Conduit errors."""

    status_code: int = 500
    error_type: str = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_response(self) -> dict[str, Any]:
        return {
            "error": {
                "message": self.message,
                "type": self.error_type,
                "code": self.status_code,
                **self.details,
            }
        }


class AuthenticationError(ConduitError):
    status_code = 401
    error_type = "authentication_error"


class AuthorizationError(ConduitError):
    status_code = 403
    error_type = "authorization_error"


class NotFoundError(ConduitError):
    status_code = 404
    error_type = "not_found"


class RateLimitError(ConduitError):
    status_code = 429
    error_type = "rate_limit_exceeded"


class BudgetExceededError(ConduitError):
    status_code = 429
    error_type = "budget_exceeded"


class ModelNotAllowedError(ConduitError):
    status_code = 403
    error_type = "model_not_allowed"


class ProviderError(ConduitError):
    status_code = 502
    error_type = "provider_error"


class NoHealthyDeploymentError(ConduitError):
    status_code = 503
    error_type = "no_healthy_deployment"


class ValidationError(ConduitError):
    status_code = 400
    error_type = "invalid_request_error"


def register_error_handlers(app: FastAPI) -> None:
    """Register global exception handlers."""

    @app.exception_handler(ConduitError)
    async def conduit_error_handler(request: Request, exc: ConduitError) -> ORJSONResponse:
        await logger.awarning(
            "conduit.error",
            error_type=exc.error_type,
            message=exc.message,
            status_code=exc.status_code,
            path=request.url.path,
        )
        return ORJSONResponse(
            status_code=exc.status_code,
            content=exc.to_response(),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> ORJSONResponse:
        await logger.aexception(
            "conduit.unhandled_error",
            path=request.url.path,
            error=str(exc),
        )
        return ORJSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "An internal error occurred.",
                    "type": "internal_error",
                    "code": 500,
                }
            },
        )