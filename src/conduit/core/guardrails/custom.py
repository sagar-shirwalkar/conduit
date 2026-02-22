"""
Custom guardrail rules — user-defined via the admin API.

Supports:
  - Regex pattern matching
  - Word list matching
  - Max token limits
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from conduit.models.guardrail_rule import GuardrailAction, GuardrailRule, GuardrailType


@dataclass
class CustomRuleResult:
    """Result of evaluating a custom rule"""

    triggered: bool
    rule_name: str
    rule_type: str
    action: str
    details: str = ""


def evaluate_custom_rule(
    rule: GuardrailRule,
    text: str,
) -> CustomRuleResult:
    """Evaluate a single custom guardrail rule against text"""

    if rule.type == GuardrailType.REGEX:
        pattern_str = rule.config.get("pattern", "")
        try:
            match = re.search(pattern_str, text, re.IGNORECASE)
            return CustomRuleResult(
                triggered=match is not None,
                rule_name=rule.name,
                rule_type=rule.type.value,
                action=rule.action.value,
                details=f"Matched pattern: {match.group()[:100]}" if match else "",
            )
        except re.error:
            return CustomRuleResult(
                triggered=False, rule_name=rule.name,
                rule_type=rule.type.value, action=rule.action.value,
            )

    elif rule.type == GuardrailType.WORD_LIST:
        words = rule.config.get("words", [])
        text_lower = text.lower()
        for word in words:
            if word.lower() in text_lower:
                return CustomRuleResult(
                    triggered=True,
                    rule_name=rule.name,
                    rule_type=rule.type.value,
                    action=rule.action.value,
                    details=f"Matched word: {word}",
                )
        return CustomRuleResult(
            triggered=False, rule_name=rule.name,
            rule_type=rule.type.value, action=rule.action.value,
        )

    elif rule.type == GuardrailType.MAX_TOKENS:
        from conduit.common.tokens import count_tokens
        max_tokens = rule.config.get("max_tokens", 100000)
        model = rule.config.get("model", "gpt-5")
        token_count = count_tokens(text, model)
        return CustomRuleResult(
            triggered=token_count > max_tokens,
            rule_name=rule.name,
            rule_type=rule.type.value,
            action=rule.action.value,
            details=f"Token count {token_count} exceeds limit {max_tokens}"
            if token_count > max_tokens else "",
        )

    return CustomRuleResult(
        triggered=False, rule_name=rule.name,
        rule_type=rule.type.value, action=rule.action.value,
    )