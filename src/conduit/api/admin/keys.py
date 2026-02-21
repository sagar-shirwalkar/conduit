"""API key management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from fastapi.responses import ORJSONResponse

from conduit.api.deps import AdminKey, DBSession
from conduit.schemas.keys import (
    APIKeyInfo,
    APIKeyListResponse,
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
    UpdateAPIKeyRequest,
)
from conduit.services.key_service import KeyService

router = APIRouter()


@router.post(
    "/",
    response_model=CreateAPIKeyResponse,
    status_code=201,
    summary="Create API key",
)
async def create_key(
    body: CreateAPIKeyRequest,
    admin_key: AdminKey,
    db: DBSession,
) -> CreateAPIKeyResponse:
    service = KeyService(db)
    return await service.create_key(body)


@router.get(
    "/",
    response_model=APIKeyListResponse,
    summary="List API keys",
)
async def list_keys(
    admin_key: AdminKey,
    db: DBSession,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> APIKeyListResponse:
    service = KeyService(db)
    return await service.list_keys(offset=offset, limit=limit)


@router.get(
    "/{key_id}",
    response_model=APIKeyInfo,
    summary="Get API key details",
)
async def get_key(
    key_id: uuid.UUID,
    admin_key: AdminKey,
    db: DBSession,
) -> APIKeyInfo:
    service = KeyService(db)
    return await service.get_key(key_id)


@router.patch(
    "/{key_id}",
    response_model=APIKeyInfo,
    summary="Update API key",
)
async def update_key(
    key_id: uuid.UUID,
    body: UpdateAPIKeyRequest,
    admin_key: AdminKey,
    db: DBSession,
) -> APIKeyInfo:
    service = KeyService(db)
    return await service.update_key(key_id, body)


@router.delete(
    "/{key_id}",
    status_code=204,
    summary="Revoke API key",
)
async def revoke_key(
    key_id: uuid.UUID,
    admin_key: AdminKey,
    db: DBSession,
) -> None:
    service = KeyService(db)
    await service.revoke_key(key_id)