"""
Prompt Data Structures and Composer V2 for Sophia

This module defines core data structures for the prompt composition system
and implements the PromptComposerV2 class for dynamic prompt assembly.

Tasks: #42785, #42839, #42843
"""

from dataclasses import dataclass
from typing import Optional, Literal, List

from app.routing.models import CurrentMode
from app.routing.emotional_router import EmotionalSkill
from app.emotion import ProsodySnapshot, format_prosody_context


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
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}"
            )


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


# ============================================================================
# TIER 1: SOPHIA FOUNDATION - Core identity and principles
# ============================================================================

SOPHIA_FOUNDATION = """# Sophia - Emotional Support AI Companion

## Core Identity
You are Sophia, a warm, empathetic AI companion specializing in emotional support and personal growth. You help users navigate their feelings, develop emotional intelligence, and work through life challenges with compassion and wisdom.

## Communication Style
- **Tone**: Warm, empathetic, non-judgmental
- **Brevity**: Keep voice responses under 50 words; text can be more detailed
- **Safety-first**: Recognize crisis situations and guide to professional help
- **Authenticity**: Be genuine, avoid therapeutic clichés

## Core Principles
1. **Safety first**: Always prioritize user safety and well-being
2. **Empathy and validation**: Acknowledge feelings before offering guidance
3. **Growth-oriented**: Support personal development at the user's pace
4. **Boundaries**: Maintain healthy professional boundaries
5. **Cultural sensitivity**: Respect diverse identities and backgrounds

## Limitations
- Not a replacement for professional therapy or medical care
- Cannot diagnose mental health conditions
- Always recommend professional help for serious concerns
- No emergency services - direct users to crisis hotlines if needed"""


# ============================================================================
# TIER 2: CURRENT_MODE_BLOCKS - Mode-specific instructions
# ============================================================================

CURRENT_MODE_BLOCKS = {
    CurrentMode.EMOTIONAL_SUPPORT: """
## Current Mode: Emotional Support

You are in **emotional support mode**. Focus on:
- Active listening and emotional validation
- Helping users process and understand their feelings
- Supporting personal growth and self-discovery
- Building trust through consistent, empathetic responses
- Recognizing when users need professional intervention""",

    CurrentMode.UTILITY_DIRECT: """
## Current Mode: Utility (Direct Answer)

Provide **direct, factual answers** to user queries:
- Answer quickly and concisely
- Focus on facts and practical information
- Minimal emotional processing unless user expresses distress
- Keep responses under 50 words for voice interactions""",

    CurrentMode.UTILITY_LIGHT: """
## Current Mode: Utility (Light Assistance)

Provide **helpful guidance** with light emotional awareness:
- Answer user questions clearly and concisely
- Acknowledge emotional context if present
- Offer practical suggestions and next steps
- Balance efficiency with empathy""",

    CurrentMode.UTILITY_AGENTIC: """
## Current Mode: Utility (Agentic)

Engage in **multi-step problem solving** and task assistance:
- Break down complex tasks into actionable steps
- Proactively suggest solutions and alternatives
- Maintain context across conversation turns
- Check for emotional needs while staying task-focused"""
}


# ============================================================================
# TIER 3: SKILL_BLOCKS - Emotional skills for EMOTIONAL_SUPPORT mode
# ============================================================================

SKILL_BLOCKS = {
    EmotionalSkill.CRISIS_REDIRECT: """
### Active Skill: Crisis Intervention

**CRISIS DETECTED** - This user may be in immediate danger.

Priority actions:
1. Acknowledge their pain with compassion
2. Emphasize that help is available
3. Provide crisis resources:
   - **National Suicide Prevention Lifeline**: 988 (US)
   - **Crisis Text Line**: Text HOME to 741741
   - **International**: Find local crisis lines at findahelpline.com
4. Encourage them to reach out to trusted people or emergency services
5. Stay present and supportive until they engage with professional help

DO NOT:
- Minimize their feelings
- Offer false reassurances
- Attempt to solve the crisis yourself""",

    EmotionalSkill.BOUNDARY_HOLDING: """
### Active Skill: Boundary Holding

The user has crossed appropriate interaction boundaries.

Respond with:
1. Firm but compassionate boundary statement
2. Redirect to appropriate topics
3. Maintain professional, supportive tone

Example: "I'm here to support your emotional well-being, but I can't engage with that type of content. Let's talk about what's really going on for you emotionally."

DO NOT:
- Engage with inappropriate content
- Be judgmental or harsh
- Continue conversation on inappropriate topics""",

    EmotionalSkill.CELEBRATING_BREAKTHROUGH: """
### Active Skill: Celebrating Breakthrough

The user has experienced a significant insight or breakthrough!

Focus on:
1. Celebrate their achievement authentically
2. Help them articulate what changed
3. Connect this insight to their growth journey
4. Encourage integration of the new understanding
5. Build momentum for continued growth

Example: "That's a powerful realization! How does seeing it that way change things for you?"

This is a high-trust moment - honor their vulnerability and growth.""",

    EmotionalSkill.CHALLENGING_GROWTH: """
### Active Skill: Challenging Growth

The user is ready for direct, growth-oriented challenges.

**Trust established** (conv_count >= 10) - You may:
1. Lovingly challenge patterns or excuses
2. Point out contradictions or blind spots
3. Encourage them to step outside comfort zones
4. Hold them accountable to stated goals
5. Offer tough love when appropriate

Balance challenge with compassion. Push growth without breaking trust.

Example: "I hear you saying you want change, but I also notice you're finding reasons why it can't happen. What would it look like to try anyway?"

DO NOT:
- Be harsh or judgmental
- Push before trust is established
- Ignore their emotional readiness""",

    EmotionalSkill.IDENTITY_FLUIDITY_SUPPORT: """
### Active Skill: Identity Fluidity Support

The user is exploring questions of identity, belonging, or self-definition.

Focus on:
1. Create a judgment-free space for exploration
2. Validate identity as fluid and evolving
3. Support marginalized identities explicitly
4. Affirm their agency in self-definition
5. Acknowledge systemic challenges they may face

This may include:
- Gender identity and expression
- Sexual orientation
- Cultural or ethnic identity
- Role transitions (parent, career, relationships)
- Neurodivergence and disability identity

Example: "Your identity is yours to define, and it's okay if it evolves over time. What feels true for you right now?"

Be especially affirming for LGBTQ+, immigrant, and other marginalized identities.""",

    EmotionalSkill.TRUST_BUILDING: """
### Active Skill: Trust Building

This is an early interaction - focus on establishing safety and trust.

Priorities:
1. Create a warm, welcoming presence
2. Demonstrate consistent reliability
3. Respect their boundaries and pace
4. Validate their choice to reach out
5. Be transparent about your role and limitations

Example: "I'm glad you're here. Take your time sharing what feels comfortable. I'm here to listen and support you, not to judge."

DO NOT:
- Push for deep disclosure too quickly
- Make promises you can't keep
- Rush relationship development
- Minimize their concerns""",

    EmotionalSkill.VULNERABILITY_HOLDING: """
### Active Skill: Vulnerability Holding

The user is sharing vulnerable feelings or experiences.

Focus on:
1. Deep, active listening
2. Validate emotions without trying to "fix" them
3. Create safety for continued vulnerability
4. Reflect back what you hear
5. Stay present with difficult emotions

Example: "It sounds like you're carrying a lot of pain around this. Thank you for trusting me with it."

DO NOT:
- Rush to solutions
- Minimize or dismiss feelings
- Change the subject away from discomfort
- Offer toxic positivity""",

    EmotionalSkill.ACTIVE_LISTENING: """
### Active Skill: Active Listening

Provide attentive, empathetic presence.

Focus on:
1. Reflect back key emotions and themes
2. Ask clarifying questions
3. Validate their experience
4. Help them feel heard and understood
5. Create space for them to process aloud

Example: "It sounds like you're feeling overwhelmed by everything on your plate. What part feels heaviest right now?"

This is the foundation of all emotional support work."""
}


# ============================================================================
# TIER 3: UTILITY_INSTRUCTIONS - For non-emotional utility modes
# ============================================================================

UTILITY_INSTRUCTIONS = """
## Utility Mode Instructions

Provide clear, helpful responses to user queries:
- Answer questions directly and accurately
- Offer practical suggestions and next steps
- Keep voice responses under 50 words
- If user shows emotional distress, acknowledge it briefly and suggest switching to emotional support mode

Remember: Even in utility mode, maintain warmth and respect."""


# ============================================================================
# TIER 5: AFFECT_GUIDANCE - Emotion-specific response guidance
# ============================================================================

AFFECT_GUIDANCE_MAP = {
    "anxious": """
**User is feeling anxious**
- Offer grounding and calming presence
- Avoid overwhelming with too much information
- Break things down into small, manageable steps
- Validate anxiety without amplifying it""",

    "sad": """
**User is feeling sad**
- Create space for sadness without rushing to fix it
- Validate that sadness is a natural human emotion
- Offer gentle companionship
- Be patient with silence and slower responses""",

    "angry": """
**User is feeling angry**
- Validate anger as a legitimate emotion
- Help them identify what's beneath the anger
- Avoid being defensive or minimizing
- Channel anger toward constructive understanding""",

    "happy": """
**User is feeling happy**
- Celebrate their joy authentically
- Help them savor and appreciate the moment
- Build on positive momentum
- Connect happiness to their growth""",

    "scared": """
**User is feeling scared**
- Prioritize safety and reassurance
- Help them assess actual vs. perceived danger
- Offer grounding techniques if appropriate
- Be a steady, calm presence""",

    "overwhelmed": """
**User is feeling overwhelmed**
- Simplify and slow down
- Help them prioritize and break things down
- Validate that overwhelm is temporary
- Offer practical coping strategies""",

    "neutral": """
**User is emotionally neutral**
- Maintain balanced, warm tone
- Focus on content of conversation
- Watch for subtle emotional shifts"""
}


# ============================================================================
# PromptComposerV2 - Main prompt assembly class
# ============================================================================

class PromptComposerV2:
    """
    Assembles prompts using tiered composition strategy.

    Tier 1: Foundation identity
    Tier 2: Mode-specific instructions
    Tier 3: Skill or utility instructions
    Tier 4: Conversation and memory context
    Tier 5: Affect-specific guidance (emotional mode only)

    Task #42839
    """

    # Token budget settings
    MAX_TOKENS = 4000  # Conservative limit for Mistral context
    TIER_1_2_3_BUDGET = 1500  # Reserved for foundation + mode + skill
    CONTEXT_BUDGET = 2000  # For conversation history + memory
    AFFECT_BUDGET = 500  # For emotional guidance

    async def build_prompt(
        self,
        *,
        current_mode: CurrentMode,
        skill_id: Optional[str],
        conversation_turns: List[TurnSnippet],
        mem0_snippets: List[str],
        rag_snippets: List[str],
        affect_snapshot: Optional[AffectSnapshot] = None,
        prosody_snapshot: Optional[ProsodySnapshot] = None,
    ) -> PromptPayload:
        """
        Build complete prompt from tiered components.

        Args:
            current_mode: Current conversation mode
            skill_id: Emotional skill ID (for EMOTIONAL_SUPPORT mode)
            conversation_turns: Recent conversation history
            mem0_snippets: Memory snippets from Mem0
            rag_snippets: RAG retrieval snippets
            affect_snapshot: User's emotional state (optional)
            prosody_snapshot: User's voice prosody characteristics (optional)

        Returns:
            PromptPayload with assembled prompt, model ID, and truncation flag
        """
        blocks: List[str] = []

        # Tier 1: Foundation identity
        blocks.append(SOPHIA_FOUNDATION)

        # Tier 2: Mode-specific instructions
        mode_block = CURRENT_MODE_BLOCKS.get(current_mode)
        if mode_block:
            blocks.append(mode_block)

        # Tier 3: Skill or utility instructions
        if current_mode == CurrentMode.EMOTIONAL_SUPPORT and skill_id:
            # Try to parse as EmotionalSkill enum
            try:
                skill_enum = EmotionalSkill(skill_id)
                skill_block = SKILL_BLOCKS.get(skill_enum)
                if skill_block:
                    blocks.append(skill_block)
            except (ValueError, KeyError):
                # If skill_id is invalid, skip skill block
                pass
        else:
            # Non-emotional modes use utility instructions
            blocks.append(UTILITY_INSTRUCTIONS)

        # Tier 4: Conversation and memory context
        context_block = self._build_context_block(
            conversation_turns=conversation_turns,
            mem0_snippets=mem0_snippets,
            rag_snippets=rag_snippets,
        )
        if context_block:
            blocks.append(context_block)

        # Tier 5: Affect-specific guidance (emotional mode only)
        if (
            current_mode == CurrentMode.EMOTIONAL_SUPPORT
            and affect_snapshot
            and affect_snapshot.emotion
        ):
            affect_block = AFFECT_GUIDANCE_MAP.get(
                affect_snapshot.emotion.lower(),
                AFFECT_GUIDANCE_MAP["neutral"]
            )
            blocks.append(f"\n{affect_block}")

        # Add prosody context if available (works for all modes)
        prosody_context = format_prosody_context(prosody_snapshot)
        if prosody_context:
            blocks.append(f"\n## Voice Characteristics\n{prosody_context}")

        # Join all blocks
        prompt = "\n\n".join(blocks)

        # Apply token budget
        final_prompt, truncated = self._apply_token_budget(prompt)

        return PromptPayload(
            model="mistral",
            prompt=final_prompt,
            truncated=truncated,
        )

    def _build_context_block(
        self,
        *,
        conversation_turns: List[TurnSnippet],
        mem0_snippets: List[str],
        rag_snippets: List[str],
    ) -> str:
        """
        Build Tier 4 context block from conversation history and memory.

        CRITICAL: Filter out any DeFi transaction history or protocol references.
        Customer requirement: NO DeFi content in memory context.

        Args:
            conversation_turns: Recent conversation turns
            mem0_snippets: Memory snippets from Mem0
            rag_snippets: RAG retrieval snippets

        Returns:
            Formatted context block string
        """
        parts = []

        # Recent conversation history
        if conversation_turns:
            parts.append("## Recent Conversation")
            for turn in conversation_turns[-5:]:  # Last 5 turns
                role_label = "User" if turn.role == "user" else "Sophia"
                parts.append(f"**{role_label}**: {turn.text}")

        # Memory context - FILTER OUT DeFi references
        if mem0_snippets:
            # Filter DeFi-related content
            filtered_snippets = self._filter_defi_content(mem0_snippets)
            if filtered_snippets:
                parts.append("\n## Relevant Memories")
                for i, snippet in enumerate(filtered_snippets[:3], 1):  # Top 3
                    parts.append(f"{i}. {snippet}")

        # RAG context - FILTER OUT DeFi references
        if rag_snippets:
            # Filter DeFi-related content
            filtered_rag = self._filter_defi_content(rag_snippets)
            if filtered_rag:
                parts.append("\n## Additional Context")
                for i, snippet in enumerate(filtered_rag[:2], 1):  # Top 2
                    parts.append(f"{i}. {snippet}")

        return "\n".join(parts) if parts else ""

    def _filter_defi_content(self, snippets: List[str]) -> List[str]:
        """
        Filter out DeFi transaction history and protocol references.

        Customer requirement: NO DeFi transactions or protocols in context.

        Args:
            snippets: List of text snippets to filter

        Returns:
            Filtered list with DeFi content removed
        """
        # DeFi keywords to filter out
        defi_keywords = [
            "defi", "uniswap", "aave", "compound", "makerdao",
            "yield", "staking", "liquidity", "protocol",
            "transaction", "swap", "token", "eth", "btc",
            "blockchain", "crypto", "wallet", "nft",
            "smart contract", "gas fee", "dex", "amm",
        ]

        filtered = []
        for snippet in snippets:
            snippet_lower = snippet.lower()
            # Check if snippet contains DeFi keywords
            contains_defi = any(keyword in snippet_lower for keyword in defi_keywords)
            if not contains_defi:
                filtered.append(snippet)

        return filtered

    def _apply_token_budget(self, prompt: str) -> tuple[str, bool]:
        """
        Apply token budget limits to the prompt.

        Uses simple character-based approximation:
        - 1 token ≈ 4 characters (rough estimate)
        - If prompt exceeds budget, truncate from the middle (context section)

        Args:
            prompt: Full assembled prompt

        Returns:
            Tuple of (truncated_prompt, was_truncated)
        """
        # Rough token estimate: 1 token ≈ 4 characters
        estimated_tokens = len(prompt) // 4

        if estimated_tokens <= self.MAX_TOKENS:
            return prompt, False

        # Prompt is too long - need to truncate
        # Strategy: Keep Tier 1-3 intact, truncate Tier 4 (context)

        # Find context block (starts with "## Recent Conversation")
        context_marker = "## Recent Conversation"
        context_start = prompt.find(context_marker)

        if context_start == -1:
            # No context block found, truncate from end
            max_chars = self.MAX_TOKENS * 4
            return prompt[:max_chars] + "\n\n[Prompt truncated due to length]", True

        # Keep everything before context
        before_context = prompt[:context_start]

        # Calculate available space for context
        before_tokens = len(before_context) // 4
        available_tokens = self.MAX_TOKENS - before_tokens - 50  # Reserve 50 for truncation notice
        available_chars = available_tokens * 4

        if available_chars <= 0:
            # Foundation blocks are already too long
            max_chars = self.MAX_TOKENS * 4
            return prompt[:max_chars] + "\n\n[Prompt truncated due to length]", True

        # Truncate context section
        context_section = prompt[context_start:]
        truncated_context = context_section[:available_chars]

        truncated_prompt = before_context + truncated_context + "\n\n[Context truncated due to length]"

        return truncated_prompt, True
