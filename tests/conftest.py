"""
Shared test fixtures.

Uses an in-memory SQLite database for unit/integration tests.
For full PostgreSQL tests, use the e2e suite with Docker.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from conduit.app import create_app
from conduit.config import Settings, get_settings
from conduit.db.session import get_db_session
from conduit.models.base import Base


# Test Settings Override

def get_test_settings() -> Settings:
    return Settings(
        env="test",
        database={"url": "sqlite+aiosqlite:///:memory:"},  # type: ignore[arg-type]
        redis={"url": "redis://localhost:6379/1"},  # type: ignore[arg-type]
        auth={"master_api_key": "test_admin_key"},  # type: ignore[arg-type]
        logging={"level": "DEBUG", "format": "console"},  # type: ignore[arg-type]
    )


# Database Fixtures

@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


# App + Client Fixtures

@pytest.fixture
async def app(test_engine: AsyncEngine) -> FastAPI:
    application = create_app()
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_settings] = get_test_settings
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def admin_headers() -> dict[str, str]:
    """Headers with admin authentication."""
    return {"Authorization": "Bearer test_admin_key"}