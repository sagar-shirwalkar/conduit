"""Prompt template version management."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.common.errors import NotFoundError
from conduit.core.prompts.template import render_template, validate_template
from conduit.models.prompt_template import PromptTemplate


class PromptRegistry:
    """Manages versioned prompt templates."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        name: str,
        template: str,
        description: str | None = None,
        variables: dict[str, Any] | None = None,
        model_hint: str | None = None,
    ) -> PromptTemplate:
        """Create a new template or a new version of an existing one."""
        # Validate the template syntax
        detected_vars = validate_template(template)

        # Find latest version
        result = await self.db.execute(
            select(func.max(PromptTemplate.version)).where(
                PromptTemplate.name == name
            )
        )
        max_version = result.scalar_one_or_none() or 0

        entry = PromptTemplate(
            name=name,
            version=max_version + 1,
            description=description,
            template=template,
            variables=variables or {v: {"type": "string", "required": True} for v in detected_vars},
            model_hint=model_hint,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def get_active(self, name: str) -> PromptTemplate:
        """Get the latest active version of a template."""
        result = await self.db.execute(
            select(PromptTemplate)
            .where(PromptTemplate.name == name, PromptTemplate.is_active.is_(True))
            .order_by(PromptTemplate.version.desc())
            .limit(1)
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise NotFoundError(f"Prompt template not found: {name}")
        return template

    async def render(self, name: str, variables: dict[str, Any]) -> str:
        """Render a template by name with the given variables."""
        template = await self.get_active(name)
        return render_template(template.template, variables)

    async def list_templates(self) -> list[PromptTemplate]:
        """List latest version of each active template."""
        # Subquery for max version per name
        subq = (
            select(
                PromptTemplate.name,
                func.max(PromptTemplate.version).label("max_v"),
            )
            .where(PromptTemplate.is_active.is_(True))
            .group_by(PromptTemplate.name)
            .subquery()
        )

        result = await self.db.execute(
            select(PromptTemplate)
            .join(
                subq,
                (PromptTemplate.name == subq.c.name)
                & (PromptTemplate.version == subq.c.max_v),
            )
            .order_by(PromptTemplate.name)
        )
        return list(result.scalars().all())

    async def get_versions(self, name: str) -> list[PromptTemplate]:
        """Get all versions of a template."""
        result = await self.db.execute(
            select(PromptTemplate)
            .where(PromptTemplate.name == name)
            .order_by(PromptTemplate.version.desc())
        )
        return list(result.scalars().all())