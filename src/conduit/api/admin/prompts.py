"""Prompt template management endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import ORJSONResponse

from conduit.api.deps import AdminKey, DBSession
from conduit.core.prompts.registry import PromptRegistry
from conduit.schemas.prompts import (
    CreatePromptRequest,
    PromptInfo,
    PromptListResponse,
    RenderPromptRequest,
    RenderPromptResponse,
)

router = APIRouter()


@router.post("/", response_model=PromptInfo, status_code=201, summary="Create prompt template")
async def create_prompt(body: CreatePromptRequest, admin_key: AdminKey, db: DBSession) -> PromptInfo:
    registry = PromptRegistry(db)
    template = await registry.create(
        name=body.name,
        template=body.template,
        description=body.description,
        variables=body.variables,
        model_hint=body.model_hint,
    )
    return _to_info(template)


@router.get("/", response_model=PromptListResponse, summary="List prompt templates")
async def list_prompts(admin_key: AdminKey, db: DBSession) -> PromptListResponse:
    registry = PromptRegistry(db)
    templates = await registry.list_templates()
    return PromptListResponse(
        templates=[_to_info(t) for t in templates],
        total=len(templates),
    )


@router.get("/{name}/versions", summary="List versions of a template")
async def list_versions(name: str, admin_key: AdminKey, db: DBSession) -> ORJSONResponse:
    registry = PromptRegistry(db)
    versions = await registry.get_versions(name)
    return ORJSONResponse(content={"versions": [_to_info(v).model_dump(mode="json") for v in versions]})


@router.post("/{name}/render", response_model=RenderPromptResponse, summary="Render template")
async def render_prompt(
    name: str, body: RenderPromptRequest, admin_key: AdminKey, db: DBSession
) -> RenderPromptResponse:
    registry = PromptRegistry(db)
    template = await registry.get_active(name)
    from conduit.core.prompts.template import render_template

    rendered = render_template(template.template, body.variables)
    return RenderPromptResponse(
        rendered=rendered,
        template_name=template.name,
        template_version=template.version,
    )


def _to_info(t) -> PromptInfo:
    return PromptInfo(
        id=t.id,
        name=t.name,
        version=t.version,
        description=t.description,
        template=t.template,
        variables=t.variables,
        model_hint=t.model_hint,
        is_active=t.is_active,
        created_at=t.created_at,
    )