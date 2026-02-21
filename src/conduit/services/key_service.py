"""API key CRUD service."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.common.crypto import generate_api_key
from conduit.common.errors import NotFoundError
from conduit.models.api_key import APIKey
from conduit.models.user import User, UserRole
from conduit.schemas.keys import (
    APIKeyInfo,
    APIKeyListResponse,
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
    UpdateAPIKeyRequest,
)


class KeyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_key(self, req: CreateAPIKeyRequest) -> CreateAPIKeyResponse:
        # Find or create user
        result = await self.db.execute(
            select(User).where(User.email == req.user_email)
        )
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                email=req.user_email,
                role=UserRole.MEMBER,
                team_id=req.team_id,
            )
            self.db.add(user)
            await self.db.flush()

        # Generate key
        raw_key, key_hash, key_prefix = generate_api_key()

        expires_at = None
        if req.expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=req.expires_in_days)

        api_key = APIKey(
            key_hash=key_hash,
            key_prefix=key_prefix,
            alias=req.alias,
            user_id=user.id,
            team_id=req.team_id,
            allowed_models=req.allowed_models,
            budget_limit_usd=req.budget_limit_usd,
            rate_limit_rpm=req.rate_limit_rpm,
            rate_limit_tpm=req.rate_limit_tpm,
            expires_at=expires_at,
        )
        self.db.add(api_key)
        await self.db.flush()

        return CreateAPIKeyResponse(
            key=raw_key,
            key_prefix=key_prefix,
            id=api_key.id,
            alias=api_key.alias,
            created_at=api_key.created_at,
        )

    async def list_keys(self, offset: int = 0, limit: int = 50) -> APIKeyListResponse:
        # Count
        count_result = await self.db.execute(select(func.count(APIKey.id)))
        total = count_result.scalar_one()

        # Fetch
        result = await self.db.execute(
            select(APIKey)
            .order_by(APIKey.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        keys = result.scalars().all()

        return APIKeyListResponse(
            keys=[self._to_info(k) for k in keys],
            total=total,
        )

    async def get_key(self, key_id: uuid.UUID) -> APIKeyInfo:
        result = await self.db.execute(
            select(APIKey).where(APIKey.id == key_id)
        )
        key = result.scalar_one_or_none()
        if key is None:
            raise NotFoundError(f"API key not found: {key_id}")
        return self._to_info(key)

    async def update_key(
        self, key_id: uuid.UUID, req: UpdateAPIKeyRequest
    ) -> APIKeyInfo:
        result = await self.db.execute(
            select(APIKey).where(APIKey.id == key_id)
        )
        key = result.scalar_one_or_none()
        if key is None:
            raise NotFoundError(f"API key not found: {key_id}")

        update_data = req.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(key, field, value)

        await self.db.flush()
        return self._to_info(key)

    async def revoke_key(self, key_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(APIKey).where(APIKey.id == key_id)
        )
        key = result.scalar_one_or_none()
        if key is None:
            raise NotFoundError(f"API key not found: {key_id}")

        key.is_active = False
        await self.db.flush()

    @staticmethod
    def _to_info(key: APIKey) -> APIKeyInfo:
        return APIKeyInfo(
            id=key.id,
            key_prefix=key.key_prefix,
            alias=key.alias,
            user_id=key.user_id,
            team_id=key.team_id,
            allowed_models=key.allowed_models,
            budget_limit_usd=key.budget_limit_usd,
            spend_usd=key.spend_usd,
            rate_limit_rpm=key.rate_limit_rpm,
            rate_limit_tpm=key.rate_limit_tpm,
            is_active=key.is_active,
            expires_at=key.expires_at,
            last_used_at=key.last_used_at,
            created_at=key.created_at,
        )