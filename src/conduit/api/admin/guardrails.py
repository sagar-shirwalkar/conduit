"""Guardrail rule management endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter

from conduit.api.deps import AdminKey, DBSession
from conduit.core.guardrails.engine import GuardrailEngine
from conduit.schemas.guardrails import (
    CreateGuardrailRuleRequest,
    GuardrailRuleInfo,
    GuardrailRuleListResponse,
    GuardrailTestRequest,
    GuardrailTestResponse,
    UpdateGuardrailRuleRequest,
)
from conduit.services.guardrail_service import GuardrailRuleService

router = APIRouter()


@router.post("/rules", response_model=GuardrailRuleInfo, status_code=201, summary="Create guardrail rule")
async def create_rule(body: CreateGuardrailRuleRequest, admin_key: AdminKey, db: DBSession) -> GuardrailRuleInfo:
    return await GuardrailRuleService(db).create_rule(body)


@router.get("/rules", response_model=GuardrailRuleListResponse, summary="List guardrail rules")
async def list_rules(admin_key: AdminKey, db: DBSession) -> GuardrailRuleListResponse:
    return await GuardrailRuleService(db).list_rules()


@router.get("/rules/{rule_id}", response_model=GuardrailRuleInfo, summary="Get guardrail rule")
async def get_rule(rule_id: uuid.UUID, admin_key: AdminKey, db: DBSession) -> GuardrailRuleInfo:
    return await GuardrailRuleService(db).get_rule(rule_id)


@router.patch("/rules/{rule_id}", response_model=GuardrailRuleInfo, summary="Update guardrail rule")
async def update_rule(
    rule_id: uuid.UUID, body: UpdateGuardrailRuleRequest, admin_key: AdminKey, db: DBSession
) -> GuardrailRuleInfo:
    return await GuardrailRuleService(db).update_rule(rule_id, body)


@router.delete("/rules/{rule_id}", status_code=204, summary="Delete guardrail rule")
async def delete_rule(rule_id: uuid.UUID, admin_key: AdminKey, db: DBSession) -> None:
    await GuardrailRuleService(db).delete_rule(rule_id)


@router.post("/test", response_model=GuardrailTestResponse, summary="Test guardrails on sample input")
async def test_guardrails(body: GuardrailTestRequest, admin_key: AdminKey, db: DBSession) -> GuardrailTestResponse:
    """Dry-run guardrails against sample messages without making an LLM call."""
    engine = GuardrailEngine(db)

    from conduit.core.guardrails.pii import redact_messages
    from conduit.core.guardrails.injection import scan_messages_injection
    from conduit.core.guardrails.content_filter import filter_messages

    _, pii_matches = redact_messages(body.messages)
    injection_result = scan_messages_injection(body.messages)
    filter_result = filter_messages(body.messages)

    try:
        guardrail_result = await engine.run_pre_request(body.messages, body.model)
        return GuardrailTestResponse(
            passed=True,
            violations=[
                {"rule": v.rule_name, "type": v.rule_type, "action": v.action, "details": v.details}
                for v in guardrail_result.violations
            ],
            pii_found=[m.type.value for m in pii_matches],
            injection_score=injection_result.score,
            content_filter_categories=list(filter_result.categories),
            modified_messages=guardrail_result.modified_messages,
        )
    except Exception as e:
        return GuardrailTestResponse(
            passed=False,
            violations=[{"rule": "engine", "type": "error", "action": "block", "details": str(e)}],
            pii_found=[m.type.value for m in pii_matches],
            injection_score=injection_result.score,
            content_filter_categories=list(filter_result.categories),
            modified_messages=None,
        )