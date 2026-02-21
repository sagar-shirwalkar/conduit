"""Model deployment management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from fastapi.responses import ORJSONResponse

from conduit.api.deps import AdminKey, DBSession
from conduit.schemas.deployments import (
    CreateDeploymentRequest,
    DeploymentInfo,
    DeploymentListResponse,
    UpdateDeploymentRequest,
)
from conduit.services.deployment_service import DeploymentService

router = APIRouter()


@router.post(
    "/",
    response_model=DeploymentInfo,
    status_code=201,
    summary="Register model deployment",
)
async def create_deployment(
    body: CreateDeploymentRequest,
    admin_key: AdminKey,
    db: DBSession,
) -> DeploymentInfo:
    service = DeploymentService(db)
    return await service.create_deployment(body)


@router.get(
    "/",
    response_model=DeploymentListResponse,
    summary="List model deployments",
)
async def list_deployments(
    admin_key: AdminKey,
    db: DBSession,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> DeploymentListResponse:
    service = DeploymentService(db)
    return await service.list_deployments(offset=offset, limit=limit)


@router.patch(
    "/{deployment_id}",
    response_model=DeploymentInfo,
    summary="Update model deployment",
)
async def update_deployment(
    deployment_id: uuid.UUID,
    body: UpdateDeploymentRequest,
    admin_key: AdminKey,
    db: DBSession,
) -> DeploymentInfo:
    service = DeploymentService(db)
    return await service.update_deployment(deployment_id, body)


@router.delete(
    "/{deployment_id}",
    status_code=204,
    summary="Remove model deployment",
)
async def delete_deployment(
    deployment_id: uuid.UUID,
    admin_key: AdminKey,
    db: DBSession,
) -> None:
    service = DeploymentService(db)
    await service.delete_deployment(deployment_id)