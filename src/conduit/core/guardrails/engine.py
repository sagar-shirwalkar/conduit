"""
Guardrails pipeline engine.

Runs pre-request and post-response guardrails in priority order.
Supports: block, redact, warn, log actions.

Pipeline:
  PRE:  PII scan → Injection detect → Content filter → Custom rules
  POST: Content filter → Custom rules

If any rule with action=block triggers, the request is rejected
immediately with a 400 error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.common.errors import ValidationError
from conduit.config import get_settings
from conduit.core.guardrails.content_filter import filter_content, filter_messages
from conduit.core.guardrails.custom import evaluate_custom_rule
from conduit.core.guardrails.injection import scan_messages_injection
from conduit.core.guardrails.pii import redact_messages, scan_pii
from conduit.models.guardrail_rule import (
    GuardrailAction,
    GuardrailRule,
    GuardrailStage,
    GuardrailType,
)

logger = structlog.stdlib.get_logger()


@dataclass
class GuardrailViolation:
    """A single guardrail violation detected during scanning."""

    rule_name: str
    rule_type: str
    action: str
    stage: str
    details: str = ""


@dataclass
class GuardrailResult:
    """Combined result of all guardrail checks."""

    passed: bool
    violations: list[GuardrailViolation] = field(default_factory=list)
    messages_modified: bool = False
    modified_messages: list[dict[str, Any]] | None = None
    pii_redacted: bool = False
    pii_types_found: set[str] = field(default_factory=set)

    @property
    def was_blocked(self) -> bool:
        return any(v.action == "block" for v in self.violations)


class GuardrailEngine:
    """
    Central guardrail pipeline executor.

    Loads rules from DB + built-in defaults, runs them in priority order.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._settings = get_settings().guardrails

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    async def _load_rules(self, stage: GuardrailStage) -> list[GuardrailRule]:
        """Load active rules from DB for a given stage."""
        result = await self.db.execute(
            select(GuardrailRule)
            .where(
                GuardrailRule.is_active.is_(True),
                GuardrailRule.stage.in_([stage, GuardrailStage.BOTH]),
            )
            .order_by(GuardrailRule.priority.asc())
        )
        return list(result.scalars().all())

    async def run_pre_request(
        self,
        messages: list[dict[str, Any]],
        model: str,
    ) -> GuardrailResult:
        """
        Run pre-request guardrails on the input messages.

        Order:
          1. Input length check
          2. PII detection + optional redaction
          3. Prompt injection detection
          4. Content filtering
          5. Custom DB rules (pre-stage)

        Returns:
            GuardrailResult (may contain modified messages if PII was redacted)
        """
        if not self.enabled:
            return GuardrailResult(passed=True)

        violations: list[GuardrailViolation] = []
        modified_msgs = messages
        pii_redacted = False
        pii_types: set[str] = set()

        # 1. Input length check
        total_length = sum(
            len(str(m.get("content", ""))) for m in messages
        )
        if total_length > self._settings.max_input_length:
            violations.append(
                GuardrailViolation(
                    rule_name="max_input_length",
                    rule_type="builtin",
                    action="block",
                    stage="pre",
                    details=f"Input length {total_length} exceeds max {self._settings.max_input_length}",
                )
            )

        # 2. PII Detection
        if self._settings.pii_enabled:
            redacted_msgs, pii_matches = redact_messages(messages)
            if pii_matches:
                pii_types = {m.type.value for m in pii_matches}

                # Default action for PII
                pii_action = self._settings.default_action

                # Check if any DB rule overrides PII behavior
                db_rules = await self._load_rules(GuardrailStage.PRE)
                for rule in db_rules:
                    if rule.type == GuardrailType.PII:
                        pii_action = rule.action.value
                        break

                if pii_action == "redact":
                    modified_msgs = redacted_msgs
                    pii_redacted = True
                    await logger.ainfo(
                        "guardrails.pii.redacted",
                        pii_types=list(pii_types),
                        count=len(pii_matches),
                    )
                elif pii_action == "block":
                    violations.append(
                        GuardrailViolation(
                            rule_name="pii_detection",
                            rule_type="pii",
                            action="block",
                            stage="pre",
                            details=f"PII detected: {', '.join(pii_types)}",
                        )
                    )
                else:  # warn / log
                    await logger.awarning(
                        "guardrails.pii.detected",
                        pii_types=list(pii_types),
                        action=pii_action,
                    )

        # 3. Prompt Injection Detection
        if self._settings.injection_enabled:
            injection_result = scan_messages_injection(modified_msgs)
            if injection_result.is_injection:
                highest = injection_result.highest_risk
                violations.append(
                    GuardrailViolation(
                        rule_name="injection_detection",
                        rule_type="injection",
                        action="block",
                        stage="pre",
                        details=(
                            f"Prompt injection detected (score: {injection_result.score:.2f}). "
                            f"Pattern: {highest.name if highest else 'unknown'}"
                        ),
                    )
                )
                await logger.awarning(
                    "guardrails.injection.detected",
                    score=injection_result.score,
                    pattern=highest.name if highest else "unknown",
                )

        # 4. Content Filter
        if self._settings.content_filter_enabled:
            filter_result = filter_messages(modified_msgs)
            if filter_result.is_flagged:
                action = (
                    "block" if filter_result.highest_severity == "high"
                    else "warn"
                )
                violations.append(
                    GuardrailViolation(
                        rule_name="content_filter",
                        rule_type="content_filter",
                        action=action,
                        stage="pre",
                        details=f"Content filter triggered: categories={filter_result.categories}",
                    )
                )

        # 5. Custom DB Rules
        db_rules = await self._load_rules(GuardrailStage.PRE)
        flat_text = " ".join(
            str(m.get("content", "")) for m in modified_msgs
        )
        for rule in db_rules:
            if rule.type in (GuardrailType.PII, GuardrailType.INJECTION, GuardrailType.CONTENT_FILTER):
                continue  # Already handled above
            result = evaluate_custom_rule(rule, flat_text)
            if result.triggered:
                violations.append(
                    GuardrailViolation(
                        rule_name=result.rule_name,
                        rule_type=result.rule_type,
                        action=result.action,
                        stage="pre",
                        details=result.details,
                    )
                )

        # Determine outcome
        has_blocking = any(v.action == "block" for v in violations)

        if has_blocking:
            blocking_violations = [v for v in violations if v.action == "block"]
            details = "; ".join(v.details for v in blocking_violations)
            raise ValidationError(
                f"Request blocked by guardrails: {details}",
                details={
                    "violations": [
                        {
                            "rule": v.rule_name,
                            "type": v.rule_type,
                            "details": v.details,
                        }
                        for v in blocking_violations
                    ]
                },
            )

        return GuardrailResult(
            passed=True,
            violations=violations,
            messages_modified=pii_redacted,
            modified_messages=modified_msgs if pii_redacted else None,
            pii_redacted=pii_redacted,
            pii_types_found=pii_types,
        )

    async def run_post_response(
        self,
        response_text: str,
        model: str,
    ) -> GuardrailResult:
        """
        Run post-response guardrails on the provider's output.

        Checks:
          1. Content filter on response
          2. Custom DB rules (post-stage)
        """
        if not self.enabled:
            return GuardrailResult(passed=True)

        violations: list[GuardrailViolation] = []

        # Content filter on response
        if self._settings.content_filter_enabled:
            filter_result = filter_content(response_text)
            if filter_result.is_flagged:
                violations.append(
                    GuardrailViolation(
                        rule_name="content_filter_response",
                        rule_type="content_filter",
                        action="warn",
                        stage="post",
                        details=f"Response content flagged: {filter_result.categories}",
                    )
                )

        # Custom DB rules (post-stage)
        db_rules = await self._load_rules(GuardrailStage.POST)
        for rule in db_rules:
            result = evaluate_custom_rule(rule, response_text)
            if result.triggered:
                violations.append(
                    GuardrailViolation(
                        rule_name=result.rule_name,
                        rule_type=result.rule_type,
                        action=result.action,
                        stage="post",
                        details=result.details,
                    )
                )

        if violations:
            await logger.awarning(
                "guardrails.post.violations",
                count=len(violations),
                rules=[v.rule_name for v in violations],
            )

        return GuardrailResult(
            passed=not any(v.action == "block" for v in violations),
            violations=violations,
        )