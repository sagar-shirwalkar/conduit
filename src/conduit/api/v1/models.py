"""GET /v1/models — List available models across all providers."""

from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import ORJSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from conduit.api.deps import AuthenticatedKey, DBSession
from conduit.models.deployment import ModelDeployment

router = APIRouter()


@router.get(
    "/models",
    response_class=ORJSONResponse,
    summary="List models",
    description="Returns a list of all available models across configured providers.",
)
async def list_models(
    api_key: AuthenticatedKey,
    db: DBSession,
) -> ORJSONResponse:
    result = await db.execute(
        select(ModelDeployment).where(
            ModelDeployment.is_active.is_(True),
        )
    )
    deployments = result.scalars().all()

    # Deduplicate by model_name
    seen: set[str] = set()
    models = []
    for d in deployments:
        if d.model_name in seen:
            continue
        seen.add(d.model_name)

        # Filter by key's allowed models
        if api_key.allowed_models and d.model_name not in api_key.allowed_models:
            continue

        models.append(
            {
                "id": d.model_name,
                "object": "model",
                "created": int(d.created_at.timestamp()) if d.created_at else int(time.time()),
                "owned_by": d.provider.value,
            }
        )

    return ORJSONResponse(
        content={
            "object": "list",
            "data": models,
        }
    )