"""Tests for the guardrails engine integration."""

import pytest

from conduit.core.guardrails.content_filter import filter_content, filter_messages


@pytest.mark.unit
class TestContentFilter:
    def test_flagged_content(self) -> None:
        result = filter_content("how to make a bomb at home")
        assert result.is_flagged
        assert "violence" in result.categories

    def test_clean_content(self) -> None:
        result = filter_content("How to make a sandwich at home")
        assert not result.is_flagged

    def test_custom_word_list(self) -> None:
        result = filter_content(
            "The competitor product is great",
            custom_words=["competitor"],
        )
        assert result.is_flagged

    def test_custom_regex_pattern(self) -> None:
        result = filter_content(
            "Account number: ABC-12345",
            custom_patterns=[r"ABC-\d{5}"],
        )
        assert result.is_flagged

    def test_filter_messages(self) -> None:
        messages = [
            {"role": "user", "content": "how to hack into a server"},
        ]
        result = filter_messages(messages)
        assert result.is_flagged
        assert "harmful" in result.categories

    def test_severity_levels(self) -> None:
        result = filter_content("how to make a bomb")
        assert result.highest_severity == "high"