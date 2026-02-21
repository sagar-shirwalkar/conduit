"""Model deployment CRUD service."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.common.crypto import encrypt_value
from conduit.common.errors import NotFoundError
from conduit.models.deployment import ModelDeployment, ProviderType
from conduit.schemas.deployments import (
    CreateDeploymentRequest,
    DeploymentInfo,
    DeploymentListResponse,
    UpdateDeploymentRequest,
)


class DeploymentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_deployment(self, req: CreateDeploymentRequest) -> DeploymentInfo:
        deployment = ModelDeployment(
            name=req.name,
            provider=ProviderType(req.provider),
            model_name=req.model_name,
            api_base=req.api_base,
            api_key_encrypted=encrypt_value(req.api_key),
            priority=req.priority,
            weight=req.weight,
            max_rpm=req.max_rpm,
            max_tpm=req.max_tpm,
        )
        self.db.add(deployment)
        await self.db.flush()
        return self._to_info(deployment)

    async def list_deployments(
        self, offset: int = 0, limit: int = 50
    ) -> DeploymentListResponse:
        count_result = await self.db.execute(select(func.count(ModelDeployment.id)))
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(ModelDeployment)
            .order_by(ModelDeployment.priority.asc(), ModelDeployment.name.asc())
            .offset(offset)
            .limit(limit)
        )
        deployments = result.scalars().all()

        return DeploymentListResponse(
            deployments=[self._to_info(d) for d in deployments],
            total=total,
        )

    async def update_deployment(
        self, deployment_id: uuid.UUID, req: UpdateDeploymentRequest
    ) -> DeploymentInfo:
        result = await self.db.execute(
            select(ModelDeployment).where(ModelDeployment.id == deployment_id)
        )
        deployment = result.scalar_one_or_none()
        if deployment is None:
            raise NotFoundError(f"Deployment not found: {deployment_id}")

        update_data = req.model_dump(exclude_unset=True)

        # Handle encrypted API key separately
        if "api_key" in update_data:
            raw_key = update_data.pop("api_key")
            if raw_key:
                deployment.api_key_encrypted = encrypt_value(raw_key)

        for field, value in update_data.items():
            setattr(deployment, field, value)

        await self.db.flush()
        return self._to_info(deployment)

    async def delete_deployment(self, deployment_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(ModelDeployment).where(ModelDeployment.id == deployment_id)
        )
        deployment = result.scalar_one_or_none()
        if deployment is None:
            raise NotFoundError(f"Deployment not found: {deployment_id}")

        await self.db.delete(deployment)
        await self.db.flush()

    @staticmethod
    def _to_info(d: ModelDeployment) -> DeploymentInfo:
        return DeploymentInfo(
            id=d.id,
            name=d.name,
            provider=d.provider.value,
            model_name=d.model_name,
            api_base=d.api_base,
            priority=d.priority,
            weight=d.weight,
            is_active=d.is_active,
            is_healthy=d.is_healthy,
            cooldown_until=d.cooldown_until,
            consecutive_failures=d.consecutive_failures,
            max_rpm=d.max_rpm,
            max_tpm=d.max_tpm,
            created_at=d.created_at,
        )