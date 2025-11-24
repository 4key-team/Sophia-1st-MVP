"""
Unit tests for prompt data structures (Task #42785)
"""

import pytest
from app.prompt.composer_v2 import AffectSnapshot, PromptPayload, TurnSnippet


class TestAffectSnapshot:
    """Tests for AffectSnapshot dataclass."""

    def test_valid_affect_snapshot_with_phoenix(self):
        """Test creating AffectSnapshot with phoenix source."""
        snapshot = AffectSnapshot(
            emotion="happy",
            confidence=0.85,
            source="phoenix"
        )
        assert snapshot.emotion == "happy"
        assert snapshot.confidence == 0.85
        assert snapshot.source == "phoenix"

    def test_valid_affect_snapshot_with_fast(self):
        """Test creating AffectSnapshot with fast source."""
        snapshot = AffectSnapshot(
            emotion="neutral",
            confidence=0.60,
            source="fast"
        )
        assert snapshot.emotion == "neutral"
        assert snapshot.confidence == 0.60
        assert snapshot.source == "fast"

    def test_valid_affect_snapshot_no_source(self):
        """Test creating AffectSnapshot with no source."""
        snapshot = AffectSnapshot(
            emotion="sad",
            confidence=0.72,
            source=None
        )
        assert snapshot.emotion == "sad"
        assert snapshot.confidence == 0.72
        assert snapshot.source is None

    def test_affect_snapshot_default_source_is_none(self):
        """Test that source defaults to None."""
        snapshot = AffectSnapshot(
            emotion="anxious",
            confidence=0.78
        )
        assert snapshot.source is None

    def test_affect_snapshot_confidence_boundaries(self):
        """Test confidence at valid boundaries."""
        # Test 0.0
        snapshot_zero = AffectSnapshot(emotion="neutral", confidence=0.0)
        assert snapshot_zero.confidence == 0.0

        # Test 1.0
        snapshot_one = AffectSnapshot(emotion="happy", confidence=1.0)
        assert snapshot_one.confidence == 1.0

    def test_affect_snapshot_invalid_confidence_too_low(self):
        """Test that confidence below 0.0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            AffectSnapshot(emotion="sad", confidence=-0.1)

    def test_affect_snapshot_invalid_confidence_too_high(self):
        """Test that confidence above 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            AffectSnapshot(emotion="happy", confidence=1.5)


class TestPromptPayload:
    """Tests for PromptPayload dataclass."""

    def test_valid_prompt_payload_not_truncated(self):
        """Test creating PromptPayload without truncation."""
        payload = PromptPayload(
            model="mistral-large-latest",
            prompt="You are Sophia, a helpful DeFi assistant.",
            truncated=False
        )
        assert payload.model == "mistral-large-latest"
        assert payload.prompt == "You are Sophia, a helpful DeFi assistant."
        assert payload.truncated is False

    def test_valid_prompt_payload_truncated(self):
        """Test creating PromptPayload with truncation."""
        payload = PromptPayload(
            model="claude-3-haiku",
            prompt="Truncated prompt...",
            truncated=True
        )
        assert payload.model == "claude-3-haiku"
        assert payload.prompt == "Truncated prompt..."
        assert payload.truncated is True

    def test_prompt_payload_default_truncated_is_false(self):
        """Test that truncated defaults to False."""
        payload = PromptPayload(
            model="gpt-4",
            prompt="Some prompt"
        )
        assert payload.truncated is False

    def test_prompt_payload_empty_prompt(self):
        """Test creating PromptPayload with empty prompt."""
        payload = PromptPayload(
            model="mistral-small",
            prompt=""
        )
        assert payload.prompt == ""
        assert payload.truncated is False

    def test_prompt_payload_long_prompt(self):
        """Test creating PromptPayload with very long prompt."""
        long_text = "A" * 10000
        payload = PromptPayload(
            model="mistral-large-latest",
            prompt=long_text,
            truncated=True
        )
        assert len(payload.prompt) == 10000
        assert payload.truncated is True


class TestTurnSnippet:
    """Tests for TurnSnippet dataclass."""

    def test_valid_turn_snippet_user(self):
        """Test creating TurnSnippet with user role."""
        turn = TurnSnippet(
            role="user",
            text="What is staking?"
        )
        assert turn.role == "user"
        assert turn.text == "What is staking?"

    def test_valid_turn_snippet_assistant(self):
        """Test creating TurnSnippet with assistant role."""
        turn = TurnSnippet(
            role="assistant",
            text="Staking is the process of locking cryptocurrency..."
        )
        assert turn.role == "assistant"
        assert turn.text == "Staking is the process of locking cryptocurrency..."

    def test_turn_snippet_empty_text(self):
        """Test creating TurnSnippet with empty text."""
        turn = TurnSnippet(role="user", text="")
        assert turn.text == ""

    def test_turn_snippet_invalid_role(self):
        """Test that invalid role raises ValueError."""
        with pytest.raises(ValueError, match="role must be 'user' or 'assistant'"):
            TurnSnippet(role="system", text="Invalid role")

    def test_turn_snippet_invalid_role_case_sensitive(self):
        """Test that role is case-sensitive."""
        with pytest.raises(ValueError, match="role must be 'user' or 'assistant'"):
            TurnSnippet(role="User", text="Wrong case")

    def test_turn_snippet_multiline_text(self):
        """Test creating TurnSnippet with multiline text."""
        multiline = """This is a long response
        that spans multiple lines
        and contains various information."""

        turn = TurnSnippet(role="assistant", text=multiline)
        assert turn.text == multiline
        assert "\n" in turn.text


class TestDataclassInteraction:
    """Tests for interactions between dataclasses."""

    def test_multiple_turn_snippets_in_conversation(self):
        """Test creating a conversation with multiple turns."""
        conversation = [
            TurnSnippet(role="user", text="Hello!"),
            TurnSnippet(role="assistant", text="Hi! How can I help?"),
            TurnSnippet(role="user", text="Explain DeFi"),
            TurnSnippet(role="assistant", text="DeFi stands for..."),
        ]

        assert len(conversation) == 4
        assert conversation[0].role == "user"
        assert conversation[1].role == "assistant"

    def test_affect_snapshot_with_prompt_payload_context(self):
        """Test using AffectSnapshot in prompt creation context."""
        affect = AffectSnapshot(
            emotion="anxious",
            confidence=0.82,
            source="phoenix"
        )

        # Simulate using affect data in prompt
        prompt_text = f"User is feeling {affect.emotion} (confidence: {affect.confidence})"
        payload = PromptPayload(
            model="mistral-large-latest",
            prompt=prompt_text
        )

        assert "anxious" in payload.prompt
        assert "0.82" in payload.prompt
