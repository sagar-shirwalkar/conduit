"""
FastAPI dependency injection.

Central place for all shared dependencies used across routes.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.common.crypto import hash_api_key
from conduit.common.errors import AuthenticationError, AuthorizationError
from conduit.config import Settings, get_settings
from conduit.db.session import get_db_session
from conduit.models.api_key import APIKey

logger = structlog.stdlib.get_logger()

# Type aliases for cleaner signatures
DBSession = Annotated[AsyncSession, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


async def get_api_key(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> APIKey:
    """
    Authenticate a request via API key.

    Accepts:
        - Authorization: Bearer cnd_sk_xxx
    """
    if not authorization:
        raise AuthenticationError("Missing Authorization header")

    # Extract the key from "Bearer <key>"
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationError("Invalid Authorization header format. Expected: Bearer <key>")

    raw_key = parts[1].strip()

    # Check if it's the master admin key
    if settings.auth.master_api_key and raw_key == settings.auth.master_api_key:
        # Return a synthetic "admin" key for master key access
        return _synthetic_admin_key()

    # Look up the hashed key in the database
    key_hash = hash_api_key(raw_key)
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True))
    )
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise AuthenticationError("Invalid API key")

    # Check expiry
    if api_key.expires_at is not None:
        from datetime import datetime, timezone

        if api_key.expires_at < datetime.now(timezone.utc):
            raise AuthenticationError("API key has expired")

    return api_key


def _synthetic_admin_key() -> APIKey:
    """Create a synthetic admin key for master key access (not stored in DB)."""
    import uuid

    key = APIKey.__new__(APIKey)
    key.id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    key.key_hash = "master"
    key.key_prefix = "cnd_admin_"
    key.alias = "master_admin"
    key.user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    key.team_id = None
    key.allowed_models = None
    key.budget_limit_usd = None
    key.spend_usd = 0
    key.rate_limit_rpm = None
    key.rate_limit_tpm = None
    key.is_active = True
    key.expires_at = None
    key.last_used_at = None
    return key


async def require_admin(
    api_key: APIKey = Depends(get_api_key),
) -> APIKey:
    """Dependency that requires admin-level access."""
    # Master admin key
    if api_key.key_hash == "master":
        return api_key

    # TODO: Check user role when user model is loaded with the key
    raise AuthorizationError("Admin access required")


# Annotated types for route signatures
AuthenticatedKey = Annotated[APIKey, Depends(get_api_key)]
AdminKey = Annotated[APIKey, Depends(require_admin)]