"""
Prompt Data Structures for Composer V2

This module defines core data structures for the prompt composition system.
Task #42785
"""

from dataclasses import dataclass
from typing import Optional, Literal


@dataclass
class AffectSnapshot:
    """
    Represents an emotional state snapshot at a specific point in time.

    Attributes:
        emotion: Emotion label (e.g., "neutral", "happy", "sad", "anxious")
        confidence: Confidence score between 0.0 and 1.0
        source: Source of the emotion analysis
                - "phoenix": Phoenix emotion analysis
                - "fast": Fast tier-0 classifier
                - None: No emotion data available
    """
    emotion: str
    confidence: float
    source: Optional[Literal["phoenix", "fast"]] = None

    def __post_init__(self):
        """Validate confidence is within valid range."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {self.confidence}")


@dataclass
class PromptPayload:
    """
    Represents the final prompt payload ready for LLM submission.

    Attributes:
        model: Model identifier (e.g., "mistral-large-latest", "claude-3-haiku")
        prompt: The complete assembled prompt text
        truncated: Whether the prompt was truncated to fit token limits
    """
    model: str
    prompt: str
    truncated: bool = False


@dataclass
class TurnSnippet:
    """
    Represents a single conversational turn in the chat history.

    Attributes:
        role: Speaker role in the conversation
              - "user": User message
              - "assistant": Assistant/Sophia response
        text: The actual message text
    """
    role: Literal["user", "assistant"]
    text: str

    def __post_init__(self):
        """Validate role is valid."""
        if self.role not in ("user", "assistant"):
            raise ValueError(f"role must be 'user' or 'assistant', got '{self.role}'")
