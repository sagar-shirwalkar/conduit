"""
PII (Personally Identifiable Information) detection and redaction.

Detects:
  - Email addresses
  - Phone numbers (US, international)
  - Social Security Numbers (US)
  - Credit card numbers (Luhn-validated)
  - IP addresses (IPv4, IPv6)
  - AWS keys
  - Custom patterns (configurable via DB rules)

No external dependencies — uses compiled regex patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PIIType(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    AWS_KEY = "aws_key"
    API_KEY = "api_key"


@dataclass
class PIIMatch:
    """A detected PII occurrence"""

    type: PIIType
    value: str
    start: int
    end: int
    redacted: str


@dataclass
class PIIScanResult:
    """Result of PII scanning a text"""

    has_pii: bool
    matches: list[PIIMatch] = field(default_factory=list)
    redacted_text: str = ""
    pii_types_found: set[str] = field(default_factory=set)


# Compiled Patterns

_PATTERNS: dict[PIIType, re.Pattern[str]] = {
    PIIType.EMAIL: re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    ),
    PIIType.PHONE: re.compile(
        r"(?<!\d)"  # negative lookbehind for digit
        r"(?:"
        r"\+?1[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"  # US
        r"|"
        r"\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}(?:[-.\s]?\d{2,4})?"  # Intl
        r")"
        r"(?!\d)"  # negative lookahead for digit
    ),
    PIIType.SSN: re.compile(
        r"\b(?!000|666|9\d{2})\d{3}[-\s]?(?!00)\d{2}[-\s]?(?!0000)\d{4}\b"
    ),
    PIIType.CREDIT_CARD: re.compile(
        r"\b(?:"
        r"4\d{3}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"  # Visa
        r"|"
        r"5[1-5]\d{2}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"  # MC
        r"|"
        r"3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}"  # Amex
        r"|"
        r"6(?:011|5\d{2})[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"  # Discover
        r")\b"
    ),
    PIIType.IPV4: re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),
    PIIType.IPV6: re.compile(
        r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
    ),
    PIIType.AWS_KEY: re.compile(
        r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"
    ),
    PIIType.API_KEY: re.compile(
        r"\b(?:sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36}|glpat-[a-zA-Z0-9\-]{20,})\b"
    ),
}

_REDACTION_MAP: dict[PIIType, str] = {
    PIIType.EMAIL: "[EMAIL_REDACTED]",
    PIIType.PHONE: "[PHONE_REDACTED]",
    PIIType.SSN: "[SSN_REDACTED]",
    PIIType.CREDIT_CARD: "[CC_REDACTED]",
    PIIType.IPV4: "[IP_REDACTED]",
    PIIType.IPV6: "[IP_REDACTED]",
    PIIType.AWS_KEY: "[AWS_KEY_REDACTED]",
    PIIType.API_KEY: "[API_KEY_REDACTED]",
}


def _luhn_check(number: str) -> bool:
    """Validate a credit card number using the Luhn algorithm"""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse = digits[::-1]
    for i, d in enumerate(reverse):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def scan_pii(
    text: str,
    pii_types: set[PIIType] | None = None,
    custom_patterns: dict[str, str] | None = None,
) -> PIIScanResult:
    """
    Scan text for PII patterns.

    Args:
        text: Input text to scan
        pii_types: Set of PII types to scan for (None = all)
        custom_patterns: Additional name→regex patterns to check

    Returns:
        PIIScanResult with all matches and the redacted text
    """
    types_to_check = pii_types or set(PIIType)
    matches: list[PIIMatch] = []

    for pii_type in types_to_check:
        pattern = _PATTERNS.get(pii_type)
        if pattern is None:
            continue

        for match in pattern.finditer(text):
            value = match.group()

            # Validate credit card with Luhn
            if pii_type == PIIType.CREDIT_CARD and not _luhn_check(value):
                continue

            matches.append(
                PIIMatch(
                    type=pii_type,
                    value=value,
                    start=match.start(),
                    end=match.end(),
                    redacted=_REDACTION_MAP.get(pii_type, "[REDACTED]"),
                )
            )

    # Custom patterns
    if custom_patterns:
        for name, pattern_str in custom_patterns.items():
            try:
                pat = re.compile(pattern_str)
                for match in pat.finditer(text):
                    matches.append(
                        PIIMatch(
                            type=PIIType.API_KEY,  # generic
                            value=match.group(),
                            start=match.start(),
                            end=match.end(),
                            redacted=f"[{name.upper()}_REDACTED]",
                        )
                    )
            except re.error:
                continue

    # Sort by descending for safe replacement
    matches.sort(key=lambda m: m.start, reverse=True)

    # Build redacted text
    redacted = text
    for m in matches:
        redacted = redacted[: m.start] + m.redacted + redacted[m.end :]

    # Resort ascending for the result
    matches.sort(key=lambda m: m.start)

    return PIIScanResult(
        has_pii=len(matches) > 0,
        matches=matches,
        redacted_text=redacted,
        pii_types_found={m.type.value for m in matches},
    )


def redact_messages(
    messages: list[dict[str, Any]],
    pii_types: set[PIIType] | None = None,
) -> tuple[list[dict[str, Any]], list[PIIMatch]]:
    """
    Scan and redact PII from a list of chat messages.

    Returns:
        (redacted_messages, all_matches)
    """
    all_matches: list[PIIMatch] = []
    redacted: list[dict[str, Any]] = []

    for msg in messages:
        new_msg = dict(msg)
        content = msg.get("content", "")

        if isinstance(content, str):
            result = scan_pii(content, pii_types)
            if result.has_pii:
                new_msg["content"] = result.redacted_text
                all_matches.extend(result.matches)

        elif isinstance(content, list):
            new_blocks = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    result = scan_pii(block.get("text", ""), pii_types)
                    if result.has_pii:
                        new_block = dict(block)
                        new_block["text"] = result.redacted_text
                        new_blocks.append(new_block)
                        all_matches.extend(result.matches)
                    else:
                        new_blocks.append(block)
                else:
                    new_blocks.append(block)
            new_msg["content"] = new_blocks

        redacted.append(new_msg)

    return redacted, all_matches