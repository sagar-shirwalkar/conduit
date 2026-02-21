"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from conduit import __version__
from conduit.api.admin.router import admin_router
from conduit.api.middleware.logging import RequestLoggingMiddleware
from conduit.api.middleware.request_id import RequestIDMiddleware
from conduit.api.v1.router import v1_router
from conduit.common.errors import register_error_handlers
from conduit.common.logging import configure_logging
from conduit.config import get_settings
from conduit.db.session import engine, async_session_factory


logger = structlog.stdlib.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle."""
    settings = get_settings()
    configure_logging(settings.logging.level, settings.logging.format)

    log = structlog.stdlib.get_logger()
    await log.ainfo(
        "conduit.startup",
        version=__version__,
        env=settings.env,
        database=settings.database.url.split("@")[-1],  # Hide credentials
    )

    # Store on app state for dependency injection
    app.state.settings = settings
    app.state.db_session_factory = async_session_factory

    yield

    # Shutdown
    await engine.dispose()
    await log.ainfo("conduit.shutdown")


def create_app() -> FastAPI:
    """Application factory — called by Uvicorn."""
    settings = get_settings()

    app = FastAPI(
        title="Conduit LLM Gateway",
        description="Self-hosted LLM gateway with unified API, auth, and observability.",
        version=__version__,
        docs_url="/docs" if settings.env == "development" else None,
        redoc_url="/redoc" if settings.env == "development" else None,
        lifespan=lifespan,
    )

    # Middleware (order matters; outermost first)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.env == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    app.include_router(v1_router)
    app.include_router(admin_router)

    return app