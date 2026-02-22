"""Tests for semantic cache components."""

import pytest

from conduit.core.cache.exact import ExactMatchCache
from conduit.core.cache.embedding import normalize_prompt_for_embedding


@pytest.mark.unit
class TestPromptNormalization:
    def test_basic_normalization(self) -> None:
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is Python?"},
        ]
        result = normalize_prompt_for_embedding(messages)
        # System messages should be skipped
        assert "You are helpful" not in result
        assert "user: What is Python?" in result

    def test_empty_messages(self) -> None:
        result = normalize_prompt_for_embedding([])
        assert result == ""

    def test_multi_turn(self) -> None:
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]
        result = normalize_prompt_for_embedding(messages)
        assert "user: Hello" in result
        assert "assistant: Hi there!" in result
        assert "user: How are you?" in result

    def test_content_blocks(self) -> None:
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "Describe this"}]},
        ]
        result = normalize_prompt_for_embedding(messages)
        assert "Describe this" in result


@pytest.mark.unit
class TestExactMatchHash:
    def test_deterministic(self) -> None:
        h1 = ExactMatchCache.compute_hash("hello", "gpt-4o")
        h2 = ExactMatchCache.compute_hash("hello", "gpt-4o")
        assert h1 == h2

    def test_model_changes_hash(self) -> None:
        h1 = ExactMatchCache.compute_hash("hello", "gpt-4o")
        h2 = ExactMatchCache.compute_hash("hello", "gpt-4o-mini")
        assert h1 != h2

    def test_content_changes_hash(self) -> None:
        h1 = ExactMatchCache.compute_hash("hello", "gpt-4o")
        h2 = ExactMatchCache.compute_hash("hello!", "gpt-4o")
        assert h1 != h2