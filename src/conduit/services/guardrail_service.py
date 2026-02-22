"""Guardrail rule CRUD service."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.common.errors import NotFoundError
from conduit.models.guardrail_rule import (
    GuardrailAction,
    GuardrailRule,
    GuardrailStage,
    GuardrailType,
)
from conduit.schemas.guardrails import (
    CreateGuardrailRuleRequest,
    GuardrailRuleInfo,
    GuardrailRuleListResponse,
    UpdateGuardrailRuleRequest,
)


class GuardrailRuleService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_rule(self, req: CreateGuardrailRuleRequest) -> GuardrailRuleInfo:
        rule = GuardrailRule(
            name=req.name,
            description=req.description,
            type=GuardrailType(req.type),
            stage=GuardrailStage(req.stage),
            action=GuardrailAction(req.action),
            config=req.config,
            priority=req.priority,
        )
        self.db.add(rule)
        await self.db.flush()
        return self._to_info(rule)

    async def list_rules(self) -> GuardrailRuleListResponse:
        count_result = await self.db.execute(select(func.count(GuardrailRule.id)))
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(GuardrailRule).order_by(GuardrailRule.priority.asc())
        )
        rules = result.scalars().all()

        return GuardrailRuleListResponse(
            rules=[self._to_info(r) for r in rules],
            total=total,
        )

    async def get_rule(self, rule_id: uuid.UUID) -> GuardrailRuleInfo:
        result = await self.db.execute(
            select(GuardrailRule).where(GuardrailRule.id == rule_id)
        )
        rule = result.scalar_one_or_none()
        if rule is None:
            raise NotFoundError(f"Guardrail rule not found: {rule_id}")
        return self._to_info(rule)

    async def update_rule(
        self, rule_id: uuid.UUID, req: UpdateGuardrailRuleRequest
    ) -> GuardrailRuleInfo:
        result = await self.db.execute(
            select(GuardrailRule).where(GuardrailRule.id == rule_id)
        )
        rule = result.scalar_one_or_none()
        if rule is None:
            raise NotFoundError(f"Guardrail rule not found: {rule_id}")

        update_data = req.model_dump(exclude_unset=True)
        if "action" in update_data:
            update_data["action"] = GuardrailAction(update_data["action"])
        for field_name, value in update_data.items():
            setattr(rule, field_name, value)

        await self.db.flush()
        return self._to_info(rule)

    async def delete_rule(self, rule_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(GuardrailRule).where(GuardrailRule.id == rule_id)
        )
        rule = result.scalar_one_or_none()
        if rule is None:
            raise NotFoundError(f"Guardrail rule not found: {rule_id}")
        await self.db.delete(rule)
        await self.db.flush()

    @staticmethod
    def _to_info(rule: GuardrailRule) -> GuardrailRuleInfo:
        return GuardrailRuleInfo(
            id=rule.id,
            name=rule.name,
            description=rule.description,
            type=rule.type.value,
            stage=rule.stage.value,
            action=rule.action.value,
            config=rule.config,
            priority=rule.priority,
            is_active=rule.is_active,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )