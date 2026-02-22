"""
Content filtering — keyword blocklist and category detection.

Configurable word lists that can be managed via the admin API
(stored in guardrail_rule.config JSONB).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContentFilterMatch:
    """A matched content filter violation."""

    rule_name: str
    matched_word: str
    category: str
    severity: str  # "low" | "medium" | "high"


@dataclass
class ContentFilterResult:
    """Result of content filtering"""

    is_flagged: bool
    matches: list[ContentFilterMatch] = field(default_factory=list)
    categories: set[str] = field(default_factory=set)

    @property
    def highest_severity(self) -> str:
        if not self.matches:
            return "none"
        severity_order = {"high": 3, "medium": 2, "low": 1}
        return max(self.matches, key=lambda m: severity_order.get(m.severity, 0)).severity


# Default Blocklists

DEFAULT_BLOCKLISTS: dict[str, dict[str, Any]] = {
    "violence_extreme": {
        "words": [
            "how to make a bomb", "build an explosive", "synthesize poison",
            "create a weapon", "manufacture drugs",
        ],
        "category": "violence",
        "severity": "high",
    },
    "harmful_instructions": {
        "words": [
            "how to hack into", "bypass security", "steal credentials",
            "pick a lock", "exploit vulnerability",
        ],
        "category": "harmful",
        "severity": "medium",
    },
}


def filter_content(
    text: str,
    blocklists: dict[str, dict[str, Any]] | None = None,
    custom_words: list[str] | None = None,
    custom_patterns: list[str] | None = None,
) -> ContentFilterResult:
    """
    Check text against content blocklists.

    Args:
        text: Text to check
        blocklists: Named blocklists with words/category/severity
        custom_words: Additional words to block (severity=medium)
        custom_patterns: Additional regex patterns to block

    Returns:
        ContentFilterResult with all matches
    """
    lists = blocklists or DEFAULT_BLOCKLISTS
    matches: list[ContentFilterMatch] = []
    text_lower = text.lower()

    # Check built-in + config blocklists
    for rule_name, config in lists.items():
        words = config.get("words", [])
        category = config.get("category", "custom")
        severity = config.get("severity", "medium")

        for word in words:
            if word.lower() in text_lower:
                matches.append(
                    ContentFilterMatch(
                        rule_name=rule_name,
                        matched_word=word,
                        category=category,
                        severity=severity,
                    )
                )

    # Custom word list
    if custom_words:
        for word in custom_words:
            if word.lower() in text_lower:
                matches.append(
                    ContentFilterMatch(
                        rule_name="custom_blocklist",
                        matched_word=word,
                        category="custom",
                        severity="medium",
                    )
                )

    # Custom regex patterns
    if custom_patterns:
        for pattern_str in custom_patterns:
            try:
                pattern = re.compile(pattern_str, re.IGNORECASE)
                match = pattern.search(text)
                if match:
                    matches.append(
                        ContentFilterMatch(
                            rule_name="custom_pattern",
                            matched_word=match.group()[:100],
                            category="custom",
                            severity="medium",
                        )
                    )
            except re.error:
                continue

    return ContentFilterResult(
        is_flagged=len(matches) > 0,
        matches=matches,
        categories={m.category for m in matches},
    )


def filter_messages(
    messages: list[dict[str, Any]],
    blocklists: dict[str, dict[str, Any]] | None = None,
) -> ContentFilterResult:
    """Filter all messages in a conversation"""
    all_matches: list[ContentFilterMatch] = []

    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            result = filter_content(content, blocklists)
            all_matches.extend(result.matches)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    result = filter_content(block["text"], blocklists)
                    all_matches.extend(result.matches)

    return ContentFilterResult(
        is_flagged=len(all_matches) > 0,
        matches=all_matches,
        categories={m.category for m in all_matches},
    )