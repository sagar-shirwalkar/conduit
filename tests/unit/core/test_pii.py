"""Tests for PII detection and redaction."""

import pytest

from conduit.core.guardrails.pii import PIIType, redact_messages, scan_pii


@pytest.mark.unit
class TestPIIScan:
    def test_detect_email(self) -> None:
        result = scan_pii("Contact me at john@example.com please")
        assert result.has_pii
        assert PIIType.EMAIL.value in result.pii_types_found
        assert "[EMAIL_REDACTED]" in result.redacted_text
        assert "john@example.com" not in result.redacted_text

    def test_detect_phone_us(self) -> None:
        result = scan_pii("Call me at +1 (555) 123-4567")
        assert result.has_pii
        assert PIIType.PHONE.value in result.pii_types_found

    def test_detect_ssn(self) -> None:
        result = scan_pii("My SSN is 123-45-6789")
        assert result.has_pii
        assert PIIType.SSN.value in result.pii_types_found
        assert "[SSN_REDACTED]" in result.redacted_text

    def test_detect_credit_card_visa(self) -> None:
        result = scan_pii("Card: 4532015112830366")
        assert result.has_pii
        assert PIIType.CREDIT_CARD.value in result.pii_types_found

    def test_invalid_credit_card_not_detected(self) -> None:
        result = scan_pii("Number: 1234567890123456")
        cc_matches = [m for m in result.matches if m.type == PIIType.CREDIT_CARD]
        assert len(cc_matches) == 0

    def test_detect_ipv4(self) -> None:
        result = scan_pii("Server at 192.168.1.100")
        assert result.has_pii
        assert PIIType.IPV4.value in result.pii_types_found

    def test_detect_aws_key(self) -> None:
        result = scan_pii("Key: AKIAIOSFODNN7EXAMPLE")
        assert result.has_pii
        assert PIIType.AWS_KEY.value in result.pii_types_found

    def test_detect_openai_key(self) -> None:
        result = scan_pii("My key is sk-abcdefghijklmnopqrstuvwxyz")
        assert result.has_pii

    def test_no_pii(self) -> None:
        result = scan_pii("The weather is nice today.")
        assert not result.has_pii
        assert result.redacted_text == "The weather is nice today."

    def test_multiple_pii_types(self) -> None:
        text = "Email john@test.com, IP 10.0.0.1, SSN 078-05-1120"
        result = scan_pii(text)
        assert result.has_pii
        assert len(result.matches) >= 3

    def test_redact_messages(self) -> None:
        messages = [
            {"role": "user", "content": "My email is test@example.com"},
            {"role": "assistant", "content": "Thanks!"},
        ]
        redacted, matches = redact_messages(messages)
        assert len(matches) == 1
        assert "test@example.com" not in redacted[0]["content"]
        assert "[EMAIL_REDACTED]" in redacted[0]["content"]
        assert redacted[1]["content"] == "Thanks!"

    def test_selective_pii_types(self) -> None:
        text = "Email: a@b.com, IP: 192.168.1.1"
        result = scan_pii(text, pii_types={PIIType.EMAIL})
        assert result.has_pii
        assert PIIType.EMAIL.value in result.pii_types_found
        assert PIIType.IPV4.value not in result.pii_types_found