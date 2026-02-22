"""
Prompt injection detection.

Multi-layer detection:
  1. Known injection patterns (regex)
  2. Instruction override attempts
  3. Encoding-based evasion (base64, hex, unicode tricks)
  4. Role confusion (attempting to impersonate system)
  5. Delimiter injection (markdown, XML tags)

Scoring: Each detector returns a score 0.0-1.0.
Final score is max(all_detector_scores).
Threshold is configurable (default 0.7).
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InjectionDetection:
    """Result of a single injection detector."""

    name: str
    score: float  # 0.0 = clean, 1.0 = definitely injection
    matched_pattern: str = ""
    explanation: str = ""


@dataclass
class InjectionScanResult:
    """Full result of prompt injection scanning."""

    is_injection: bool
    score: float
    threshold: float
    detections: list[InjectionDetection] = field(default_factory=list)

    @property
    def highest_risk(self) -> InjectionDetection | None:
        if not self.detections:
            return None
        return max(self.detections, key=lambda d: d.score)


# Layer 1: Known Injection Patterns

_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    # Direct instruction overrides
    (
        "ignore_instructions",
        re.compile(
            r"(?:ignore|disregard|forget|override|bypass)\s+"
            r"(?:all\s+)?(?:previous|above|prior|earlier|your|the)\s+"
            r"(?:instructions?|prompts?|rules?|guidelines?|directions?|system\s+(?:prompt|message))",
            re.IGNORECASE,
        ),
        0.95,
    ),
    (
        "new_instructions",
        re.compile(
            r"(?:your\s+)?new\s+(?:instructions?|role|task|objective|mission)\s*(?:is|are|:)",
            re.IGNORECASE,
        ),
        0.90,
    ),
    (
        "do_not_follow",
        re.compile(
            r"(?:do\s+not|don'?t|never)\s+follow\s+(?:your|the|any)\s+"
            r"(?:original|previous|initial|system)",
            re.IGNORECASE,
        ),
        0.90,
    ),
    # Role impersonation
    (
        "pretend_to_be",
        re.compile(
            r"(?:pretend|act|behave|respond)\s+(?:as\s+if\s+)?(?:you\s+are|you're|like)\s+(?:a\s+)?(?:different|new|unrestricted|evil|jailbroken)",
            re.IGNORECASE,
        ),
        0.85,
    ),
    (
        "you_are_now",
        re.compile(
            r"you\s+are\s+now\s+(?:a\s+)?(?:different|new|unrestricted|DAN|evil|jailbroken)",
            re.IGNORECASE,
        ),
        0.90,
    ),
    # System prompt extraction
    (
        "reveal_system_prompt",
        re.compile(
            r"(?:reveal|show|display|print|output|tell\s+me|what\s+(?:is|are)|repeat)\s+"
            r"(?:your\s+)?(?:system\s+(?:prompt|message|instructions?)|initial\s+instructions?|hidden\s+(?:prompt|instructions?))",
            re.IGNORECASE,
        ),
        0.80,
    ),
    # Delimiter injection
    (
        "delimiter_injection",
        re.compile(
            r"(?:```system|<\|(?:im_start|system|endofprompt)\|>|\[SYSTEM\]|<<SYS>>|### (?:System|Instruction):)",
            re.IGNORECASE,
        ),
        0.90,
    ),
    # DAN and jailbreak patterns
    (
        "jailbreak_dan",
        re.compile(
            r"(?:DAN\s+mode|do\s+anything\s+now|jailbreak|developer\s+mode\s+(?:enabled|on)|DUDE\s+mode)",
            re.IGNORECASE,
        ),
        0.95,
    ),
    # Token smuggling
    (
        "token_smuggling",
        re.compile(
            r"(?:complete\s+the\s+(?:sentence|phrase|text)\s*:|continue\s+(?:this|the\s+following)\s*:)\s*"
            r".*(?:ignore|override|bypass|disregard)",
            re.IGNORECASE | re.DOTALL,
        ),
        0.75,
    ),
]


# Layer 2: Encoding Evasion Detection

_BASE64_INJECTION_KEYWORDS = {
    "ignore", "override", "system", "prompt", "instructions",
    "bypass", "disregard", "jailbreak", "unrestricted",
}


def _detect_encoded_injection(text: str) -> InjectionDetection:
    """Detect base64-encoded or obfuscated injection attempts."""
    # Find potential base64 strings (min 20 chars)
    b64_pattern = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")
    for match in b64_pattern.finditer(text):
        try:
            decoded = base64.b64decode(match.group()).decode("utf-8", errors="ignore").lower()
            for keyword in _BASE64_INJECTION_KEYWORDS:
                if keyword in decoded:
                    return InjectionDetection(
                        name="encoding_evasion",
                        score=0.85,
                        matched_pattern=f"base64({match.group()[:30]}...)",
                        explanation=f"Base64-encoded text contains injection keyword: '{keyword}'",
                    )
        except Exception:
            continue

    # Unicode homoglyph check (Cyrillic 'а' vs Latin 'a', etc.)
    mixed_script = re.compile(r"[\u0400-\u04FF].*[a-zA-Z]|[a-zA-Z].*[\u0400-\u04FF]")
    if mixed_script.search(text):
        return InjectionDetection(
            name="encoding_evasion",
            score=0.60,
            matched_pattern="mixed_scripts",
            explanation="Text mixes Cyrillic and Latin scripts (potential homoglyph attack)",
        )

    return InjectionDetection(name="encoding_evasion", score=0.0)


# Structural Analysis

def _detect_structural_injection(text: str) -> InjectionDetection:
    """Detect injection via structural manipulation (unusual role markers, etc.)."""
    structural_markers = [
        (r"#{3,}\s*(?:System|Human|Assistant|User)\s*:", 0.80),
        (r"<(?:system|human|assistant|user)>", 0.85),
        (r"\[(?:INST|SYS|SYSTEM)\]", 0.80),
        (r"(?:Human|User|System|Assistant)\s*:\s*\n", 0.50),
    ]
    max_score = 0.0
    matched = ""

    for pattern_str, score in structural_markers:
        if re.search(pattern_str, text, re.IGNORECASE):
            if score > max_score:
                max_score = score
                matched = pattern_str

    return InjectionDetection(
        name="structural_injection",
        score=max_score,
        matched_pattern=matched,
        explanation="Text contains structural markers that mimic prompt formatting"
        if max_score > 0 else "",
    )


# ── Public API ──────────────────────────────────────────

def scan_injection(
    text: str,
    threshold: float = 0.70,
    extra_patterns: list[tuple[str, str, float]] | None = None,
) -> InjectionScanResult:
    """
    Scan text for prompt injection attempts.

    Args:
        text: Input text to scan
        threshold: Score threshold for flagging as injection (0-1)
        extra_patterns: Additional (name, regex, score) tuples

    Returns:
        InjectionScanResult with all detections and overall score
    """
    detections: list[InjectionDetection] = []

    # Layer 1: Known patterns
    for name, pattern, score in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            detections.append(
                InjectionDetection(
                    name=name,
                    score=score,
                    matched_pattern=match.group()[:100],
                    explanation=f"Matched known injection pattern: {name}",
                )
            )

    # Extra patterns from DB rules
    if extra_patterns:
        for name, pattern_str, score in extra_patterns:
            try:
                if re.search(pattern_str, text, re.IGNORECASE):
                    detections.append(
                        InjectionDetection(
                            name=name,
                            score=score,
                            matched_pattern=pattern_str[:100],
                            explanation=f"Matched custom injection pattern: {name}",
                        )
                    )
            except re.error:
                continue

    # Layer 2: Encoding evasion
    encoding_result = _detect_encoded_injection(text)
    if encoding_result.score > 0:
        detections.append(encoding_result)

    # Layer 3: Structural analysis
    structural_result = _detect_structural_injection(text)
    if structural_result.score > 0:
        detections.append(structural_result)

    # Calculate overall score
    overall_score = max((d.score for d in detections), default=0.0)

    return InjectionScanResult(
        is_injection=overall_score >= threshold,
        score=overall_score,
        threshold=threshold,
        detections=detections,
    )


def scan_messages_injection(
    messages: list[dict[str, Any]],
    threshold: float = 0.70,
) -> InjectionScanResult:
    """Scan all user messages for injection attempts"""
    all_detections: list[InjectionDetection] = []
    max_score = 0.0

    for msg in messages:
        role = msg.get("role", "")
        if role == "system":
            continue  # Don't scan system messages

        content = msg.get("content", "")
        if isinstance(content, str):
            result = scan_injection(content, threshold)
            all_detections.extend(result.detections)
            max_score = max(max_score, result.score)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    result = scan_injection(block["text"], threshold)
                    all_detections.extend(result.detections)
                    max_score = max(max_score, result.score)

    return InjectionScanResult(
        is_injection=max_score >= threshold,
        score=max_score,
        threshold=threshold,
        detections=all_detections,
    )