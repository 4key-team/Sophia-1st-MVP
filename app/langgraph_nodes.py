"""LangGraph state machine defining audio ingestion, intent analysis, response, and TTS nodes."""

import asyncio
import logging
import threading
import time
import uuid
from enum import Enum
from typing import Callable, Dict, Any, Optional, List, TypedDict, Sequence
from dataclasses import dataclass

from langgraph.graph import StateGraph, START, END

from app.services.mistral import (
    transcribe_audio_with_voxtral,
    generate_llm_reply,
)
from app.services.emotion import (
    analyze_emotion_audio,
    infer_text_emotion,
    trigger_phoenix_bg,
)
from app.services.emotional_guidance import (
    get_guidance as get_emotional_guidance,
    format_guidance_block,
)
from app.services.tts import synthesize_inworld
from app.services.supabase import upload_audio_and_get_url
from app.services.memory import memory_manager, ConversationTurn
from app.services.rag import rag_system
from app.services.memo import memo_client  # Task #42597
from app.services.prompt_composer import prompt_composer  # Task #42597
from app.config import get_settings
from app.routing.intent_router import classify_intent_and_mode
from app.routing.models import CurrentMode, Intent, UtilityPath

logger = logging.getLogger(__name__)

# Task #42729: Mode routing constants
MODE_DIRECT = CurrentMode.UTILITY_DIRECT.value
MODE_LIGHT = CurrentMode.UTILITY_LIGHT.value
MODE_UTILITY_AGENTIC = CurrentMode.UTILITY_AGENTIC.value
MODE_EMOTIONAL_SUPPORT = CurrentMode.EMOTIONAL_SUPPORT.value


@dataclass
class EmotionData:
    label: str
    confidence: float


class ResponsePath(str, Enum):
    DIRECT = "direct"
    LIGHT = "light"
    AGENTIC = "agentic"


CancelCallback = Callable[[], None]


class GraphState(TypedDict):
    session_id: str
    audio_bytes: bytes
    transcript: str
    user_emotion: EmotionData
    intent: str
    current_mode: str  # Task #42729: Routing mode
    utility_path: Optional[str]
    router_path: str
    context_memory: Dict[str, Any]
    memo_context: Dict[str, Any]  # Task #42597: MemO intelligent memory context
    llm_response: str
    response_path: str
    sophia_emotion: EmotionData
    is_mock_audio: bool
    audio_url: str
    tts_bytes: bytes
    evaluation_logs: List[Dict[str, Any]]
    emotion_guidance: List[str]
    fallback_used: Dict[str, str]
    use_voxtral_large: bool  # Flag to indicate if Voxtral Large pipeline is active
    cancel_check: Optional[CancelCallback]


def _maybe_cancel(state: GraphState) -> None:
    cancel = state.get("cancel_check")
    if callable(cancel):
        cancel()


def _raise_if_cancelled(exc: Exception) -> None:
    if isinstance(exc, asyncio.CancelledError):
        raise exc


def _ensure_emotion_guidance(state: GraphState) -> List[str]:
    """Populate emotion guidance in state with a single lookup per turn."""
    guidance = state.get("emotion_guidance")
    if guidance:
        return guidance

    label = getattr(state.get("user_emotion"), "label", "neutral")
    guidance = get_emotional_guidance(label)
    state["emotion_guidance"] = guidance

    if guidance:
        preview = "; ".join(guidance[:2])
        logger.info(
            "Emotion guidance applied for %s: %s%s",
            label,
            preview,
            "..." if len(guidance) > 2 else "",
        )
    else:
        logger.info("Emotion guidance lookup for %s returned empty result.", label)

    return guidance


class AudioIngestor:
    """Takes audio and determines processing pipeline - Voxtral Large vs Legacy"""

    def __init__(self, use_voxtral_large: bool = True):
        self.settings = get_settings()
        self.use_voxtral_large = use_voxtral_large
        logger.info(
            f"AudioIngestor initialized (Voxtral Large preference: {use_voxtral_large})"
        )

    def __call__(self, state: GraphState) -> GraphState:
        logger.info(f"AudioIngestor processing session {state['session_id']}")
        state.setdefault("fallback_used", {})
        _maybe_cancel(state)

        # Import shared services
        from app.services.shared_services import shared_services

        if self.use_voxtral_large and shared_services.is_voxtral_large_available():
            # VOXTRAL LARGE PATH: Extract transcript for IntentAnalyzer, defer response to ResponseGenerator
            logger.info("AudioIngestor: Using Voxtral Large pipeline")
            try:
                _maybe_cancel(state)
                # Quick validation that audio is processable
                if not state.get("audio_bytes") or len(state["audio_bytes"]) < 1000:
                    raise ValueError("Audio data too small or empty")

                # Get shared service and extract transcript for IntentAnalyzer
                hybrid_service = shared_services.get_hybrid_voxtral_service()
                if not hybrid_service:
                    raise Exception("Shared HybridVoxtralService not available")

                # Extract transcript using Voxtral Large (for IntentAnalyzer to work)
                _maybe_cancel(state)
                transcript = hybrid_service.primary._transcribe_audio(
                    state["audio_bytes"]
                )

                if not transcript or not transcript.strip():
                    logger.warning(
                        "AudioIngestor: Voxtral Large returned empty transcript, falling back to legacy STT"
                    )
                    state["fallback_used"]["audio_ingestor"] = "empty_transcript"
                    state["use_voxtral_large"] = False
                    return self._legacy_audio_ingestion(state)

                # Analyze emotion from audio
                user_emotion = analyze_emotion_audio(state["audio_bytes"])

                # Set pipeline flags and populate transcript for IntentAnalyzer
                state["use_voxtral_large"] = True
                state["transcript"] = (
                    transcript  # Now IntentAnalyzer can work properly!
                )
                state["user_emotion"] = EmotionData(
                    label=user_emotion.label, confidence=user_emotion.confidence
                )

                logger.info(
                    f"AudioIngestor (Voxtral Large) completed: transcript='{transcript[:50]}...', "
                    f"emotion={user_emotion.label}({user_emotion.confidence:.2f})"
                )

            except Exception as e:
                logger.warning(
                    f"AudioIngestor: Voxtral Large processing failed, falling back: {e}"
                )
                _raise_if_cancelled(e)
                state["fallback_used"]["audio_ingestor"] = "voxtral_large_failed"
                state["use_voxtral_large"] = False
                return self._legacy_audio_ingestion(state)
        else:
            # LEGACY PATH: Full processing
            logger.info("AudioIngestor: Using legacy STT pipeline")
            state["use_voxtral_large"] = False
            return self._legacy_audio_ingestion(state)

        return state

    def _legacy_audio_ingestion(self, state: GraphState) -> GraphState:
        """Legacy audio ingestion using separate STT"""
        try:
            _maybe_cancel(state)
            # Transcribe using Voxtral + Phoenix emotion analysis
            transcript = transcribe_audio_with_voxtral(
                state["audio_bytes"], cancel_check=state.get("cancel_check")
            )
            logger.debug(
                "AudioIngestor: transcribe_audio_with_voxtral returned %s (len=%d)",
                repr(transcript[:75] if isinstance(transcript, str) else transcript),
                len(transcript) if isinstance(transcript, str) else -1,
            )

            # Try Whisper immediately if Voxtral produced an empty transcript
            if not transcript or (
                isinstance(transcript, str) and not transcript.strip()
            ):
                logger.warning(
                    "AudioIngestor: Voxtral returned empty transcript, trying Whisper fallback"
                )
                state["fallback_used"]["stt"] = "voxtral_empty_whisper_fallback"
                transcript = self._whisper_fallback(state, state["audio_bytes"])
                whisper_preview = (
                    transcript[:50] if isinstance(transcript, str) else transcript
                )
                logger.info(
                    "AudioIngestor: Whisper fallback returned %s (len=%d)",
                    repr(whisper_preview),
                    len(transcript) if isinstance(transcript, str) else -1,
                )
            user_emotion = analyze_emotion_audio(state["audio_bytes"])

            state["transcript"] = transcript
            if not transcript or (
                isinstance(transcript, str) and not transcript.strip()
            ):
                logger.error(
                    "❌ AudioIngestor produced EMPTY transcript for session %s after all fallbacks!",
                    state["session_id"],
                )
                transcript_preview = "EMPTY"
            else:
                transcript_preview = (
                    transcript[:50] if isinstance(transcript, str) else transcript
                )
            state["user_emotion"] = EmotionData(
                label=user_emotion.label, confidence=user_emotion.confidence
            )

            logger.info(
                "AudioIngestor completed: transcript='%s...', emotion=%s(%.2f)",
                transcript_preview,
                user_emotion.label,
                user_emotion.confidence,
            )

        except Exception as e:
            logger.error(f"AudioIngestor failed: {e}")
            _raise_if_cancelled(e)
            # Set fallback flag and try Whisper fallback
            state["fallback_used"]["stt"] = "whisper_fallback"
            _maybe_cancel(state)
            state["transcript"] = self._whisper_fallback(state, state["audio_bytes"])
            logger.debug(
                "AudioIngestor: whisper fallback returned %s (len=%d)",
                repr(
                    state["transcript"][:75]
                    if isinstance(state["transcript"], str)
                    else state["transcript"]
                ),
                len(state["transcript"])
                if isinstance(state["transcript"], str)
                else -1,
            )
            if not state["transcript"]:
                logger.warning(
                    "AudioIngestor whisper fallback produced empty transcript for session %s",
                    state["session_id"],
                )
            # Still analyze emotion with Phoenix
            user_emotion = analyze_emotion_audio(state["audio_bytes"])
            state["user_emotion"] = EmotionData(
                label=user_emotion.label, confidence=user_emotion.confidence
            )

        return state

    def _whisper_fallback(self, state: GraphState, audio_bytes: bytes) -> str:
        """Fallback to OpenAI Whisper for STT"""
        try:
            _maybe_cancel(state)
            import openai

            client = openai.OpenAI(api_key=self.settings.OPENAI_API_KEY)

            # Convert bytes to file-like object
            import io

            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "audio.wav"

            transcript = client.audio.transcriptions.create(
                model="whisper-1", file=audio_file
            )
            return transcript.text
        except Exception as e:
            logger.error(f"Whisper fallback failed: {e}")
            _raise_if_cancelled(e)
            return ""


class IntentAnalyzer:
    """Classifies intent and routing mode via centralized intent router."""

    def __call__(self, state: GraphState) -> GraphState:
        logger.info(f"IntentAnalyzer processing session {state['session_id']}")

        transcript = state.get("transcript") or ""
        logger.debug(
            "IntentAnalyzer: received transcript %s (len=%d)",
            repr(transcript[:75] if isinstance(transcript, str) else transcript),
            len(transcript) if isinstance(transcript, str) else -1,
        )
        if not transcript:
            logger.warning(
                "IntentAnalyzer received empty transcript for session %s",
                state["session_id"],
            )

        try:
            _maybe_cancel(state)
            result = self._run_intent_router(transcript, state)
            state["intent"] = result.intent.value
            state["current_mode"] = result.current_mode.value
            state["utility_path"] = (
                result.utility_path.value if result.utility_path else None
            )
            state["router_path"] = self._map_router_path(result.current_mode)

            logger.info(
                "IntentAnalyzer completed: intent=%s mode=%s router_path=%s",
                state["intent"],
                state["current_mode"],
                state["router_path"],
            )
        except Exception as exc:
            logger.exception("IntentAnalyzer failed, using safe defaults: %s", exc)
            _raise_if_cancelled(exc)
            state["intent"] = Intent.EMOTIONAL_SUPPORT.value
            state["current_mode"] = MODE_EMOTIONAL_SUPPORT
            state["utility_path"] = None
            state["router_path"] = "emotional"

        return state

    def _run_intent_router(self, transcript: str, state: GraphState):
        async def _classify():
            return await classify_intent_and_mode(
                user_message=transcript,
                session_id=state["session_id"],
                prosody=None,
            )

        try:
            loop = asyncio.get_running_loop()
            loop_running = loop.is_running()
        except RuntimeError:
            loop = None
            loop_running = False

        if not loop_running:
            return asyncio.run(_classify())

        result_container: Dict[str, Any] = {}
        error_container: List[BaseException] = []

        def _worker():
            try:
                result_container["result"] = asyncio.run(_classify())
            except BaseException as exc:
                error_container.append(exc)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        thread.join()

        if error_container:
            raise error_container[0]
        return result_container["result"]

    def _map_router_path(self, current_mode: CurrentMode) -> str:
        """Map CurrentMode enum to compact router_path string for metrics."""
        if isinstance(current_mode, CurrentMode):
            mode_value = current_mode.value
        else:
            mode_value = str(current_mode).lower()

        match mode_value:
            case CurrentMode.EMOTIONAL_SUPPORT.value:
                return "emotional"
            case CurrentMode.UTILITY_DIRECT.value:
                return "direct"
            case CurrentMode.UTILITY_LIGHT.value:
                return "light"
            case _:
                return "agentic"


class ResponseGenerator:
    """Generates responses using appropriate pipeline based on AudioIngestor decision"""

    def __init__(self, use_voxtral_large: bool = True):
        self.settings = get_settings()
        self.use_voxtral_large = use_voxtral_large
        self._response_path_split = getattr(
            self.settings, "ENABLE_RESPONSE_PATH_SPLIT", False
        )
        logger.info(
            f"ResponseGenerator initialized (Voxtral Large preference: {use_voxtral_large})"
        )

    def __call__(self, state: GraphState) -> GraphState:
        logger.info(f"ResponseGenerator processing session {state['session_id']}")
        state.setdefault("fallback_used", {})
        _maybe_cancel(state)

        # Task #42729: Check current_mode for routing
        mode = self._normalize_mode(state.get("current_mode", MODE_LIGHT))
        state["current_mode"] = mode
        logger.info(f"ResponseGenerator using mode: {mode}")

        try:
            # Route based on mode
            if mode == MODE_DIRECT:
                return self._process_direct_mode(state)
            elif mode == MODE_EMOTIONAL_SUPPORT:
                return self._process_emotional_support_mode(state)
            elif mode == MODE_UTILITY_AGENTIC:
                return self._process_utility_agentic_mode(state)
            else:  # MODE_LIGHT or fallback
                return self._process_light_mode(state)

        except Exception as e:
            logger.error(f"ResponseGenerator failed: {e}")
            _raise_if_cancelled(e)
            _maybe_cancel(state)
            # Final fallback to Claude-3
            state["fallback_used"]["llm"] = "claude_fallback"
            response = self._claude_fallback(
                state.get("transcript", ""),
                state.get("intent", ""),
                cancel_check=state.get("cancel_check"),
            )
            state["llm_response"] = response

        return state

    def _normalize_mode(self, mode_value: Any) -> str:
        """Normalize mode value from enums/legacy strings to canonical strings."""
        if isinstance(mode_value, CurrentMode):
            return mode_value.value

        if isinstance(mode_value, str):
            value = mode_value.lower()
            mapping = {
                "direct": MODE_DIRECT,
                "utility_direct": MODE_DIRECT,
                "light": MODE_LIGHT,
                "utility_light": MODE_LIGHT,
                "agentic": MODE_UTILITY_AGENTIC,
                "utility_agentic": MODE_UTILITY_AGENTIC,
                "emotional_support": MODE_EMOTIONAL_SUPPORT,
            }
            return mapping.get(value, MODE_LIGHT)

        return MODE_LIGHT

    def _process_with_voxtral_large(self, state: GraphState) -> GraphState:
        """Process using Voxtral Large unified pipeline (transcript already extracted by AudioIngestor)"""
        from app.services.shared_services import shared_services

        logger.info("ResponseGenerator: Processing with Voxtral Large")
        state["response_path"] = ResponsePath.AGENTIC.value
        cancel_check = state.get("cancel_check")

        try:
            hybrid_service = shared_services.get_hybrid_voxtral_service()
            if not hybrid_service:
                raise Exception("Shared HybridVoxtralService not available")

            # Build context for Voxtral Large (transcript already available from AudioIngestor)
            context_dict = self._build_voxtral_context(state)

            # Use Voxtral Large for response generation with built-in fallback logic
            # Build a comprehensive system prompt using existing transcript and context (Task #42597: with MemO)
            system_prompt = self._build_voxtral_system_prompt(
                intent=state.get("intent", ""),
                memo_context=state.get("memo_context"),
                user_emotion=state["user_emotion"].label,
                emotion_guidance=context_dict.get("emotion_guidance"),
            )
            prompt_with_context = self._build_voxtral_prompt_with_context(
                state["transcript"], context_dict, system_prompt
            )

            # Generate response using HybridVoxtralService (includes fallback logic)
            result = hybrid_service.generate_response(
                state["audio_bytes"],
                context=context_dict,
                system_prompt=prompt_with_context,
                fallback_on_error=True,
                cancel_check=cancel_check,
            )

            # Extract response and log which service was used
            state["llm_response"] = result["response"]

            # Track fallbacks used by the hybrid service
            if result["service_used"] != "voxtral_large":
                logger.warning(
                    f"HybridVoxtralService used fallback: {result['service_used']}"
                )
                state["fallback_used"]["hybrid_service"] = result["service_used"]

            logger.info(
                f"ResponseGenerator (Voxtral Large) completed: "
                f"transcript='{state['transcript'][:50]}...', "
                f"response='{state['llm_response'][:50]}...'"
            )

        except Exception as e:
            logger.warning(
                f"ResponseGenerator Voxtral Large failed, falling back to legacy: {e}"
            )
            _raise_if_cancelled(e)
            _maybe_cancel(state)
            state["fallback_used"]["response_generator"] = "voxtral_large_failed"
            state["use_voxtral_large"] = False

            # Emergency fallback: ensure we have a transcript for legacy processing
            if not state.get("transcript"):
                try:
                    state["transcript"] = transcribe_audio_with_voxtral(
                        state["audio_bytes"],
                        cancel_check=cancel_check,
                    )
                    user_emotion = analyze_emotion_audio(state["audio_bytes"])
                    state["user_emotion"] = EmotionData(
                        label=user_emotion.label, confidence=user_emotion.confidence
                    )
                except Exception as fallback_error:
                    logger.error(
                        f"Emergency transcript fallback failed: {fallback_error}"
                    )
                    state["transcript"] = "I couldn't process your audio."
                    state["user_emotion"] = EmotionData(label="neutral", confidence=0.5)

            # Process with legacy LLM
            return self._process_with_legacy_llm(state)

        return state

    def _process_with_legacy_llm(self, state: GraphState) -> GraphState:
        """Process using legacy LLM pipeline"""
        logger.info("ResponseGenerator: Processing with legacy LLM")
        _maybe_cancel(state)
        cancel_check = state.get("cancel_check")

        if not self._response_path_split:
            state["response_path"] = ResponsePath.AGENTIC.value
            state["llm_response"] = self._generate_agentic_response(
                state, cancel_check=cancel_check
            )
            logger.info(
                "ResponseGenerator response-path split disabled; forcing AGENTIC for session %s",
                state["session_id"],
            )
            return state

        self._seed_emotion_from_affect_snapshot(state)
        path = self._select_response_path(state)
        state["response_path"] = path.value

        if path is ResponsePath.DIRECT:
            self._launch_phoenix_background(state)
            state["llm_response"] = self._generate_direct_snippet(state)
            logger.info(
                "ResponseGenerator selected DIRECT path for session %s",
                state["session_id"],
            )
            return state

        if path is ResponsePath.LIGHT:
            self._launch_phoenix_background(state)
            state["llm_response"] = self._generate_light_response(
                state, cancel_check=cancel_check
            )
            logger.info(
                "ResponseGenerator selected LIGHT path for session %s",
                state["session_id"],
            )
            return state

        state["llm_response"] = self._generate_agentic_response(
            state, cancel_check=cancel_check
        )
        logger.info(
            "ResponseGenerator selected AGENTIC path for session %s: response='%s...'",
            state["session_id"],
            state["llm_response"][:50],
        )
        return state

    def _build_voxtral_context(self, state: GraphState) -> Dict[str, Any]:
        """Build rich context dictionary for Voxtral Large"""
        # Get memory context
        memory_context = memory_manager.get_context_for_llm(
            state["session_id"], access_token=state.get("supabase_token")
        )
        state["context_memory"] = memory_context

        # Task #42597: Get MemO intelligent memory
        memo_memories = []
        try:
            # Extract user_id from session (assuming session_id format or use default)
            user_id = state.get("user_id", state["session_id"])
            memo_memories = asyncio.run(
                memo_client.search_memories(
                    user_id=user_id, query_text=state["transcript"], top_k=3
                )
            )
            if memo_memories:
                logger.info(f"MemO: Retrieved {len(memo_memories)} relevant memories")
        except Exception as e:
            logger.warning(f"MemO memory retrieval failed: {e}")

        state["memo_context"] = {"memories": memo_memories}

        # Build context dictionary
        context = {
            "intent": state["intent"],
            "user_emotion": {
                "label": state["user_emotion"].label,
                "confidence": state["user_emotion"].confidence,
            },
        }

        emotion_guidance = _ensure_emotion_guidance(state)
        if emotion_guidance:
            context["emotion_guidance"] = emotion_guidance

        # Add memory context
        if "last_topics" in memory_context:
            context["last_topics"] = memory_context["last_topics"]
        if "last_user_tone" in memory_context:
            context["last_user_tone"] = memory_context["last_user_tone"]
        if "recent_intents" in memory_context:
            context["recent_intents"] = memory_context["recent_intents"]

        # Add MemO context
        if memo_memories:
            context["memo_memories"] = memo_memories

        # Add RAG context for DeFi questions
        if state["intent"] == "defi_question":
            # We need the transcript for RAG lookup (already extracted by AudioIngestor)
            rag_context = rag_system.get_context_for_llm(state["transcript"])
            if rag_context:
                context["rag_context"] = rag_context
                logger.info(f"RAG context added: {len(rag_context)} characters")

        return context

    def _build_context(self, state: GraphState) -> str:
        """Build context from memory and current state"""
        context = self._ensure_flash_context(state)
        memo_context = self._ensure_memo_context(state)

        context_parts = []
        if "last_topics" in context and context["last_topics"]:
            context_parts.append(
                f"Previous topics: {', '.join(context['last_topics'])}"
            )
        if "last_user_tone" in context:
            context_parts.append(
                f"User's recent emotional state: {context['last_user_tone']}"
            )
        if "recent_intents" in context and context["recent_intents"]:
            context_parts.append(
                f"Recent conversation types: {', '.join(context['recent_intents'])}"
            )

        # Add MemO context to string
        memories = memo_context.get("memories", []) if memo_context else []
        if memories:
            memo_texts = []
            for mem in memories[:2]:
                memo_texts.append(mem.get("text") or mem.get("memory_text", ""))
            if memo_texts:
                context_parts.append(f"User memories: {'; '.join(memo_texts)}")

        history_block = self._format_recent_turns_for_prompt(
            context.get("recent_turns")
        )
        if history_block:
            context_parts.append(f"Recent conversation:\n{history_block}")

        return " | ".join(context_parts) if context_parts else ""

    def _format_recent_turns_for_prompt(
        self, recent_turns: Optional[Sequence[Dict[str, Any]]], *, max_turns: int = 3
    ) -> str:
        """Format recent user/Sophia turns into a compact prompt snippet."""
        if not recent_turns:
            return ""

        trimmed = [
            turn for turn in recent_turns if turn.get("user") or turn.get("sophia")
        ]
        if not trimmed:
            return ""

        lines: List[str] = []
        for turn in trimmed[-max_turns:]:
            user_line = (turn.get("user") or "").strip()
            sophia_line = (turn.get("sophia") or "").strip()
            if user_line:
                lines.append(f"User: {user_line}")
            if sophia_line:
                lines.append(f"Sophia: {sophia_line}")
        return "\n".join(lines)

    def _build_voxtral_system_prompt(
        self,
        intent: str,
        memo_context: Dict[str, Any] = None,
        user_emotion: str = None,
        emotion_guidance: Optional[Sequence[str]] = None,
    ) -> str:
        """Build system prompt for Voxtral Large based on intent using PromptComposer (Task #42597)"""
        # Use PromptComposer to build dynamic prompt with memory context
        system_prompt = prompt_composer.compose_system_prompt(
            memory_context=memo_context,
            user_emotion=user_emotion,
            emotion_guidance=emotion_guidance,
        )

        # Add intent-specific guidance
        if intent == "defi_question":
            system_prompt += "\n\nFocus: Provide accurate, educational DeFi guidance. Keep responses under 50 words."
        elif intent == "emotional_support":
            system_prompt += "\n\nFocus: Provide supportive and encouraging responses. Keep responses under 50 words."
        else:
            system_prompt += "\n\nFocus: Engage in friendly casual conversation. Keep responses under 50 words."

        return system_prompt

    def _build_voxtral_prompt_with_context(
        self, transcript: str, context_dict: Dict[str, Any], system_prompt: str
    ) -> str:
        """Build comprehensive prompt for Voxtral Large with context"""
        prompt_parts = [system_prompt]

        # Add conversation memory
        if "last_topics" in context_dict and context_dict["last_topics"]:
            prompt_parts.append(
                f"Previous topics: {', '.join(context_dict['last_topics'])}"
            )

        # Add emotional context
        if "user_emotion" in context_dict:
            emotion_label = context_dict["user_emotion"].get("label", "neutral")
            emotion_conf = context_dict["user_emotion"].get("confidence", 0.0)
            prompt_parts.append(
                f"User appears {emotion_label} (confidence: {emotion_conf:.2f})"
            )

        emotion_guidance = context_dict.get("emotion_guidance") or []
        guidance_block = format_guidance_block(emotion_guidance)
        if guidance_block:
            prompt_parts.append(guidance_block)
            logger.info(
                "Voxtral system prompt guidance applied: %s%s",
                "; ".join(emotion_guidance[:2]),
                "..." if len(emotion_guidance) > 2 else "",
            )

        # Add RAG context for DeFi questions
        if "rag_context" in context_dict and context_dict["rag_context"]:
            prompt_parts.append(
                f"Relevant knowledge base:\n{context_dict['rag_context']}"
            )

        prompt_parts.append(f"User question: {transcript}")

        return " | ".join(prompt_parts)

    def _prosody_present(self, state: GraphState) -> bool:
        audio_bytes = state.get("audio_bytes")
        return bool(audio_bytes and len(audio_bytes) > 0)

    def _launch_phoenix_background(self, state: GraphState) -> None:
        transcript = state.get("transcript", "")
        if not transcript:
            return
        try:
            trigger_phoenix_bg(
                state["session_id"], transcript, self._prosody_present(state)
            )
        except Exception as exc:
            logger.warning("Phoenix background trigger failed: %s", exc)

    def _seed_emotion_from_affect_snapshot(
        self, state: GraphState
    ) -> Optional[Dict[str, Any]]:
        try:
            snapshot = memory_manager.peek_affect(state["session_id"])
        except Exception as exc:
            logger.warning("Affect snapshot lookup failed: %s", exc)
            return None

        if not snapshot:
            return None

        state["affect_snapshot"] = snapshot
        current = state.get("user_emotion")
        current_label = getattr(current, "label", "neutral")
        current_conf = getattr(current, "confidence", 0.0)

        if current_label == "neutral" or current_conf < 0.55:
            new_label = snapshot.get("emotion", current_label)
            try:
                new_conf = float(snapshot.get("confidence", current_conf or 0.6))
            except (TypeError, ValueError):
                new_conf = 0.6
            state["user_emotion"] = EmotionData(label=new_label, confidence=new_conf)
            logger.info(
                "Seeded user emotion from affect snapshot for %s → %s (%.2f)",
                state["session_id"],
                new_label,
                new_conf,
            )
        return snapshot

    def _select_response_path(self, state: GraphState) -> ResponsePath:
        transcript = (state.get("transcript") or "").strip()
        if not transcript or self._looks_like_greeting(transcript):
            return ResponsePath.DIRECT

        if (state.get("intent") or "").lower() == "defi_question":
            return ResponsePath.AGENTIC

        flash_context = self._ensure_flash_context(state)
        if (
            flash_context.get("last_topics")
            or flash_context.get("recent_intents")
            or flash_context.get("conversation_turns", 0) > 0
        ):
            return ResponsePath.AGENTIC

        if len(transcript.split()) <= 40:
            return ResponsePath.LIGHT

        return ResponsePath.AGENTIC

    @staticmethod
    def _looks_like_greeting(transcript: str) -> bool:
        normalized = (transcript or "").strip().lower()
        if not normalized:
            return True
        greetings = {
            "hi",
            "hey",
            "hello",
            "yo",
            "gm",
            "sup",
            "привет",
            "здравствуй",
        }
        if normalized in greetings:
            return True
        for token in ("hey", "hi", "hello", "hola", "привет"):
            if normalized.startswith(f"{token} "):
                return True
        return False

    _DIRECT_NEGATIVE_EMOTIONS = {"sad", "anxious", "grief", "panic"}
    _DIRECT_NEGATIVE_RESPONSE = "I'm here. We can take this one step at a time."
    _DIRECT_DEFAULT_RESPONSE = (
        "Hi—I'm here with you. What would you like to talk about?"
    )

    def _generate_direct_snippet(self, state: GraphState) -> str:
        emotion_label = getattr(state.get("user_emotion"), "label", "neutral").lower()
        if emotion_label in self._DIRECT_NEGATIVE_EMOTIONS:
            return self._DIRECT_NEGATIVE_RESPONSE
        return self._DIRECT_DEFAULT_RESPONSE

    _EMOTION_TONE = {
        "joy": "celebratory yet grounded",
        "sad": "gentle and reassuring",
        "anxious": "steady and calming",
        "angry": "calm, validating, and steady",
        "fearful": "soothing and protective",
        "excited": "enthusiastic but focused",
    }

    def _map_emotion_to_tone(self, label: str) -> str:
        safe_label = (label or "neutral").lower()
        return self._EMOTION_TONE.get(safe_label, "calm and confident")

    def _generate_light_response(
        self, state: GraphState, cancel_check: Optional[CancelCallback]
    ) -> str:
        transcript = state.get("transcript", "")
        tone = self._map_emotion_to_tone(state["user_emotion"].label)
        system_prompt = (
            "You are Sophia, a concise companion. Keep replies under three sentences, "
            f"use a {tone} tone, and offer one actionable next step when helpful."
        )
        if cancel_check:
            cancel_check()
        return generate_llm_reply(
            transcript,
            cancel_check=cancel_check,
            system_prompt=system_prompt,
            max_tokens=180,
        )

    def _generate_agentic_response(
        self, state: GraphState, cancel_check: Optional[CancelCallback]
    ) -> str:
        transcript = state.get("transcript", "")
        flash_context = self._ensure_flash_context(state)
        memo_context = self._ensure_memo_context(state)
        emotion_guidance = _ensure_emotion_guidance(state)

        rag_context = ""
        if (state.get("intent") or "").lower() == "defi_question":
            try:
                rag_context = rag_system.get_context_for_llm(transcript)
                if rag_context:
                    logger.info(
                        "RAG context retrieved for session %s: %d chars",
                        state["session_id"],
                        len(rag_context),
                    )
            except Exception as exc:
                logger.warning("RAG context lookup failed: %s", exc)
                rag_context = ""

        additional_context = self._build_agentic_additional_context(
            flash_context, rag_context
        )
        system_prompt = prompt_composer.compose_system_prompt(
            memory_context=memo_context,
            user_emotion=state["user_emotion"].label,
            additional_context=additional_context,
            emotion_guidance=emotion_guidance,
        )
        user_prompt = self._build_agentic_user_prompt(
            transcript, state["user_emotion"], flash_context, rag_context
        )

        if cancel_check:
            cancel_check()
        return generate_llm_reply(
            user_prompt,
            cancel_check=cancel_check,
            system_prompt=system_prompt,
            max_tokens=256,
        )

    def _ensure_flash_context(self, state: GraphState) -> Dict[str, Any]:
        context = state.get("context_memory")
        if context:
            return context
        try:
            context = memory_manager.get_context_for_llm(
                state["session_id"], access_token=state.get("supabase_token")
            )
        except Exception as exc:
            logger.warning("Flash memory retrieval failed: %s", exc)
            context = {}
        state["context_memory"] = context or {}
        return state["context_memory"]

    def _ensure_memo_context(self, state: GraphState) -> Dict[str, Any]:
        memo_context = state.get("memo_context") or {}
        if memo_context.get("memories"):
            return memo_context
        try:
            user_id = state.get("user_id", state["session_id"])
            memo_context = asyncio.run(
                memo_client.get_context_for_llm(
                    user_id=user_id,
                    current_query=state.get("transcript", ""),
                    access_token=state.get("supabase_token"),
                )
            )
        except Exception as exc:
            logger.warning("MemO context retrieval failed: %s", exc)
            memo_context = {
                "memories": [],
                "memory_summary": "error retrieving memories",
            }
        state["memo_context"] = memo_context
        return memo_context

    def _build_agentic_additional_context(
        self, flash_context: Dict[str, Any], rag_context: str
    ) -> str:
        sections: List[str] = []
        flash_block = self._format_flash_context_for_prompt(flash_context)
        if flash_block:
            sections.append("Flash memory snapshot:\n" + flash_block)
        history_block = self._format_recent_turns_for_prompt(
            flash_context.get("recent_turns")
        )
        if history_block:
            sections.append("Conversation history:\n" + history_block)
        if rag_context:
            sections.append(f"Knowledge snippets:\n{rag_context}")
        return "\n\n".join(sections)

    def _format_flash_context_for_prompt(self, context: Dict[str, Any]) -> str:
        if not context:
            return ""
        parts: List[str] = []
        if context.get("last_topics"):
            parts.append(f"Recent topics: {', '.join(context['last_topics'])}")
        if context.get("last_user_tone"):
            parts.append(f"Previous user tone: {context['last_user_tone']}")
        if context.get("recent_intents"):
            parts.append(
                f"Recent conversation intents: {', '.join(context['recent_intents'])}"
            )
        if context.get("conversation_turns"):
            parts.append(f"Stored turns: {context['conversation_turns']}")
        return "\n".join(parts)

    def _build_agentic_user_prompt(
        self,
        transcript: str,
        user_emotion: EmotionData,
        flash_context: Dict[str, Any],
        rag_context: str,
    ) -> str:
        parts = [
            f"The user currently feels {user_emotion.label} (confidence {user_emotion.confidence:.2f})."
        ]
        if flash_context.get("last_topics"):
            parts.append(
                f"They were previously discussing: {', '.join(flash_context['last_topics'])}."
            )
        history_block = self._format_recent_turns_for_prompt(
            flash_context.get("recent_turns"), max_turns=2
        )
        if history_block:
            parts.append(f"Conversation so far:\n{history_block}")
        parts.append(f"Latest message: {transcript}")
        if rag_context:
            parts.append(f"Relevant knowledge:\n{rag_context}")
        return " | ".join(parts)

    def _process_direct_mode(self, state: GraphState) -> GraphState:
        """DIRECT mode: Skip Mem0, skip RAG, use Voxtral-only path (Task #42729)"""
        logger.info("ResponseGenerator: DIRECT mode - fast path without memory/RAG")

        # Skip memory retrieval
        state["memo_context"] = {"memories": []}
        state["context_memory"] = {}

        # Use simple, fast response
        state["llm_response"] = self._generate_simple_greeting(state["transcript"])
        return state

    def _process_light_mode(self, state: GraphState) -> GraphState:
        """LIGHT mode: Include Mem0, use PromptComposer + Mistral (Task #42729)"""
        logger.info("ResponseGenerator: LIGHT mode - standard path with memory")

        # Use existing logic with Mem0 + PromptComposer
        use_voxtral_large = state.get("use_voxtral_large", False)
        if use_voxtral_large:
            return self._process_with_voxtral_large(state)
        else:
            return self._process_with_legacy_llm(state)

    def _process_utility_agentic_mode(self, state: GraphState) -> GraphState:
        """UTILITY_AGENTIC mode: Route to reflection subgraph (Task #42729 - placeholder)"""
        logger.info("ResponseGenerator: UTILITY_AGENTIC mode - complex analysis")

        # TODO: Implement reflection subgraph routing in future
        # For now, use enhanced LIGHT mode with note about analysis
        result_state = self._process_light_mode(state)

        # Add prefix indicating analytical processing
        result_state["llm_response"] = result_state["llm_response"]
        logger.info(
            "UTILITY_AGENTIC: Using LIGHT mode as placeholder (reflection subgraph TBD)"
        )

        return result_state

    def _process_emotional_support_mode(self, state: GraphState) -> GraphState:
        """EMOTIONAL_SUPPORT mode: Pass to emotional skill router (Task #42729 - placeholder)"""
        logger.info(
            "ResponseGenerator: EMOTIONAL_SUPPORT mode - emotional support routing"
        )

        # TODO: Implement emotional skill router in future
        # For now, enhance emotional guidance in existing pipeline
        emotion_guidance = _ensure_emotion_guidance(state)

        # Force emotional support focus in prompt
        logger.info(
            f"EMOTIONAL_SUPPORT: Enhanced emotional guidance with {len(emotion_guidance)} tips"
        )

        # Use LIGHT mode with enhanced emotional context
        result_state = self._process_light_mode(state)

        return result_state

    def _generate_simple_greeting(self, transcript: str) -> str:
        """Generate simple greeting response for DIRECT mode"""
        import random

        greetings = [
            "Hello! How can I help you today?",
            "Hi there! What brings you here?",
            "Hey! Nice to see you!",
            "Hello! I'm here to assist you.",
        ]
        return random.choice(greetings)

    def _claude_fallback(
        self,
        transcript: str,
        intent: str,
        cancel_check: Optional[CancelCallback] = None,
    ) -> str:
        """Fallback to Claude-3 if Mistral fails"""
        try:
            if cancel_check:
                cancel_check()
            import anthropic

            client = anthropic.Anthropic(api_key=self.settings.ANTHROPIC_API_KEY)

            # Build system prompt based on intent
            if intent == "defi_question":
                system_prompt = "You are Sophia, a knowledgeable DeFi mentor. Provide clear, educational responses about DeFi concepts. Keep responses under 50 words."
            elif intent == "emotional_support":
                system_prompt = "You are Sophia, an empathetic AI companion. Provide supportive and encouraging responses. Keep responses under 50 words."
            else:
                system_prompt = "You are Sophia, a friendly AI assistant. Engage in casual conversation. Keep responses under 50 words."

            response = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=150,
                system=system_prompt,
                messages=[{"role": "user", "content": transcript}],
            )
            if cancel_check:
                cancel_check()

            return response.content[0].text.strip()

        except Exception as e:
            logger.error(f"Claude fallback failed: {e}")
            return (
                "I apologize, but I'm having technical difficulties. Please try again."
            )


class TTSNode:
    """Converts response to audio + analyzes Sophia's emotion"""

    def __call__(self, state: GraphState) -> GraphState:
        logger.info(f"TTSNode processing session {state['session_id']}")
        _maybe_cancel(state)

        try:
            # Synthesize with Inworld/Boson AI
            logger.info(
                f"TTSNode: Calling Inworld TTS for text: '{state['llm_response'][:50]}...'"
            )
            tts_bytes = tts_bytes = synthesize_inworld(
                state["llm_response"],
                cancel_check=state.get("cancel_check"),
            )

            logger.info(f"TTSNode: Received {len(tts_bytes)} bytes from Inworld")

            # Check for mock audio
            is_mock = tts_bytes.startswith(b"ID3mock") or len(tts_bytes) < 100
            if is_mock:
                logger.warning(
                    "TTSNode: Received mock audio from Inworld (likely API key issue)"
                )
                raise Exception("Mock audio received - triggering fallback")

            # Upload and get URL
            file_name = f"sophia_{int(time.time() * 1000)}_{state['session_id']}.mp3"
            logger.info(f"TTSNode: Uploading to Supabase as {file_name}")

            audio_url = upload_audio_and_get_url(
                file_bytes=tts_bytes, file_name=file_name
            )

            logger.info(f"TTSNode: Successfully uploaded to {audio_url}")

            # Analyze Sophia's emotion from TTS output
            sophia_emotion = analyze_emotion_audio(tts_bytes)

            state["tts_bytes"] = tts_bytes
            state["audio_url"] = audio_url
            state["is_mock_audio"] = is_mock
            state["sophia_emotion"] = EmotionData(
                label=sophia_emotion.label, confidence=sophia_emotion.confidence
            )

            logger.info(
                f"TTSNode completed: audio_url={audio_url}, "
                f"sophia_emotion={sophia_emotion.label}({sophia_emotion.confidence:.2f})"
            )

        except Exception as e:
            logger.error(f"❌ TTSNode Inworld failed: {type(e).__name__}: {str(e)}")
            _raise_if_cancelled(e)
            _maybe_cancel(state)

            # Log detailed error info
            import traceback

            logger.error(f"📋 TTSNode error traceback:\n{traceback.format_exc()}")

            # Fallback to OpenAI TTS
            state["fallback_used"]["tts"] = "openai_fallback"
            try:
                logger.info("TTSNode: Attempting OpenAI TTS fallback")
                tts_bytes = self._openai_tts_fallback(
                    state["llm_response"], cancel_check=state.get("cancel_check")
                )

                if not tts_bytes or len(tts_bytes) < 100:
                    raise Exception("OpenAI TTS returned no/invalid audio")

                file_name = f"sophia_fallback_{int(time.time() * 1000)}_{state['session_id']}.mp3"
                logger.info(f"TTSNode fallback: Uploading OpenAI audio as {file_name}")

                audio_url = upload_audio_and_get_url(
                    file_bytes=tts_bytes, file_name=file_name
                )
                sophia_emotion = analyze_emotion_audio(tts_bytes)

                state["tts_bytes"] = tts_bytes
                state["audio_url"] = audio_url
                state["sophia_emotion"] = EmotionData(
                    label=sophia_emotion.label, confidence=sophia_emotion.confidence
                )
                logger.info(f"✅ TTSNode fallback succeeded: {audio_url}")

            except Exception as fallback_error:
                logger.error(
                    f"❌ TTS fallback also failed: {type(fallback_error).__name__}: {str(fallback_error)}"
                )
                logger.error(f"📋 Fallback error traceback:\n{traceback.format_exc()}")
                _raise_if_cancelled(fallback_error)

                # Final fallback - empty audio but continue
                state["audio_url"] = ""
                state["sophia_emotion"] = EmotionData(label="neutral", confidence=0.5)
                logger.warning("⚠️ TTSNode: Using empty audio URL as final fallback")

        return state

    def _openai_tts_fallback(
        self, text: str, cancel_check: Optional[CancelCallback] = None
    ) -> bytes:
        """Fallback TTS using OpenAI"""
        try:
            import openai

            settings = get_settings()

            if cancel_check:
                cancel_check()

            if not settings.OPENAI_API_KEY:
                logger.error("OpenAI API key not configured")
                return b""

            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

            response = client.audio.speech.create(
                model="tts-1",
                voice="nova",  # Changed from "alloy" for better female voice
                input=text,
                response_format="mp3",
            )
            if cancel_check:
                cancel_check()
            return response.content

        except Exception as e:
            logger.error(f"OpenAI TTS fallback failed: {e}")
            return b""


class EvalLogger:
    """Logs latency, emotions, and fallbacks"""

    def __call__(self, state: GraphState) -> GraphState:
        logger.info(f"EvalLogger processing session {state['session_id']}")

        # Create evaluation log entry
        eval_entry = {
            "session_id": state["session_id"],
            "timestamp": time.time(),
            "user_emotion": {
                "label": state["user_emotion"].label,
                "confidence": state["user_emotion"].confidence,
            },
            "sophia_emotion": {
                "label": state["sophia_emotion"].label,
                "confidence": state["sophia_emotion"].confidence,
            },
            "intent": state["intent"],
            "current_mode": state.get("current_mode"),
            "utility_path": state.get("utility_path"),
            "router_path": state.get("router_path"),
            "fallbacks_used": state.get("fallback_used", {}),
            "transcript_length": len(state["transcript"]),
            "response_length": len(state["llm_response"]),
        }

        # Add to evaluation logs
        if "evaluation_logs" not in state:
            state["evaluation_logs"] = []
        state["evaluation_logs"].append(eval_entry)

        # Update session memory
        conversation_turn = ConversationTurn(
            query=state["transcript"],
            response=state["llm_response"],
            user_emotion=state["user_emotion"].label,
            sophia_emotion=state["sophia_emotion"].label,
            intent=state["intent"],
            timestamp=time.time(),
        )
        memory_manager.update_session_memory(
            state["session_id"],
            conversation_turn,
            access_token=state.get("supabase_token"),
        )

        # Task #42597: Extract and store important information in MemO
        try:
            user_id = state.get("user_id", state["session_id"])
            asyncio.run(
                self._extract_and_store_memories(
                    user_id=user_id,
                    session_id=state["session_id"],
                    transcript=state["transcript"],
                    response=state["llm_response"],
                    intent=state["intent"],
                    user_emotion=state["user_emotion"].label,
                )
            )
        except Exception as e:
            logger.warning(f"MemO memory storage failed: {e}")

        # Log to console for debugging
        logger.info(f"EvalLogger completed: {eval_entry}")

        return state

    async def _extract_and_store_memories(
        self,
        user_id: str,
        session_id: str,
        transcript: str,
        response: str,
        intent: str,
        user_emotion: str,
    ):
        """Extract and store important memories from conversation (Task #42597)"""
        memories_to_store = []

        # Extract preferences from transcript
        preference_keywords = [
            "i prefer",
            "i like",
            "i love",
            "i want",
            "i need",
            "my favorite",
        ]
        if any(keyword in transcript.lower() for keyword in preference_keywords):
            memories_to_store.append(
                {"text": transcript, "type": "preference", "importance": 0.8}
            )

        # Extract emotional patterns
        if user_emotion in ["excited", "happy", "sad", "anxious", "angry"]:
            if len(transcript) > 20:  # Only store meaningful emotional context
                memories_to_store.append(
                    {
                        "text": f"User expressed {user_emotion} emotion: {transcript}",
                        "type": "emotion",
                        "importance": 0.6,
                    }
                )

        # Extract factual information (names, projects, important context)
        fact_keywords = [
            "i am",
            "i'm",
            "my name is",
            "i work",
            "i study",
            "i'm working on",
        ]
        if any(keyword in transcript.lower() for keyword in fact_keywords):
            memories_to_store.append(
                {"text": transcript, "type": "fact", "importance": 0.9}
            )

        # Store all extracted memories
        for memory in memories_to_store:
            try:
                await memo_client.store_memory(
                    user_id=user_id,
                    session_id=session_id,
                    memory_text=memory["text"],
                    memory_type=memory["type"],
                    importance=memory["importance"],
                )
                logger.info(f"MemO: Stored {memory['type']} memory for user {user_id}")
            except Exception as e:
                logger.warning(f"Failed to store {memory['type']} memory: {e}")


class SophiaLangGraph:
    """Main LangGraph orchestrator"""

    def __init__(self):
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine (Task #42729: with ModeClassifier)"""

        # Initialize nodes
        audio_ingestor = AudioIngestor()
        intent_analyzer = IntentAnalyzer()
        response_generator = ResponseGenerator()
        tts_node = TTSNode()
        eval_logger = EvalLogger()

        # Create state graph
        workflow = StateGraph(GraphState)

        # Add nodes
        workflow.add_node("audio_ingestor", audio_ingestor)
        workflow.add_node("intent_analyzer", intent_analyzer)
        workflow.add_node("response_generator", response_generator)
        workflow.add_node("tts_node", tts_node)
        workflow.add_node("eval_logger", eval_logger)

        # Define edges (workflow sequence with intent/mode classification inside IntentAnalyzer)
        workflow.add_edge(START, "audio_ingestor")
        workflow.add_edge("audio_ingestor", "intent_analyzer")
        workflow.add_edge("intent_analyzer", "response_generator")
        workflow.add_edge("response_generator", "tts_node")
        workflow.add_edge("tts_node", "eval_logger")
        workflow.add_edge("eval_logger", END)

        return workflow.compile()

    def process_conversation(
        self,
        audio_bytes: bytes,
        session_id: Optional[str] = None,
        supabase_token: Optional[str] = None,
        cancel_check: Optional[CancelCallback] = None,
    ) -> GraphState:
        """Process a complete conversation turn through the graph"""

        if not session_id:
            session_id = str(uuid.uuid4())

        # Initialize state
        initial_state: GraphState = {
            "session_id": session_id,
            "audio_bytes": audio_bytes,
            "transcript": "",
            "user_emotion": EmotionData(label="neutral", confidence=0.0),
            "intent": "",
            "current_mode": MODE_LIGHT,  # Default mode, overwritten by IntentAnalyzer
            "utility_path": UtilityPath.LIGHT.value,
            "router_path": "light",
            "context_memory": {},
            "memo_context": {},  # Task #42597: MemO context
            "llm_response": "",
            "response_path": ResponsePath.AGENTIC.value,
            "sophia_emotion": EmotionData(label="neutral", confidence=0.0),
            "is_mock_audio": False,
            "audio_url": "",
            "tts_bytes": b"",
            "evaluation_logs": [],
            "emotion_guidance": [],
            "fallback_used": {},
            "use_voxtral_large": False,  # Will be set by AudioIngestor
            "supabase_token": supabase_token,
            "cancel_check": cancel_check,
        }

        logger.info(f"Starting LangGraph processing for session {session_id}")

        # Execute the graph
        final_state = self.graph.invoke(initial_state)

        logger.info(f"LangGraph processing completed for session {session_id}")

        return final_state

    def process_text_conversation(
        self,
        message: str,
        session_id: Optional[str] = None,
        supabase_token: Optional[str] = None,
        cancel_check: Optional[CancelCallback] = None,
    ) -> GraphState:
        """Process a text-only conversation turn, bypassing audio processing"""

        if not session_id:
            session_id = str(uuid.uuid4())

        # Initialize state with text message directly
        initial_state: GraphState = {
            "session_id": session_id,
            "audio_bytes": b"",  # Empty for text input
            "transcript": message,  # Use the text message directly
            "user_emotion": EmotionData(label="neutral", confidence=0.7),
            "intent": "",
            "current_mode": MODE_LIGHT,  # Default mode, overwritten by IntentAnalyzer
            "utility_path": UtilityPath.LIGHT.value,
            "router_path": "light",
            "context_memory": {},
            "llm_response": "",
            "memo_context": {"memories": []},
            "response_path": ResponsePath.AGENTIC.value,
            "sophia_emotion": EmotionData(label="neutral", confidence=0.0),
            "is_mock_audio": False,
            "audio_url": "",
            "tts_bytes": b"",
            "evaluation_logs": [],
            "emotion_guidance": [],
            "fallback_used": {},
            "use_voxtral_large": False,  # Text-only uses legacy pipeline
            "supabase_token": supabase_token,
            "cancel_check": cancel_check,
        }

        inferred = infer_text_emotion(message)
        initial_state["user_emotion"] = EmotionData(
            label=inferred.label, confidence=inferred.confidence
        )

        logger.info(
            f"Starting LangGraph text processing for session {session_id} with message: '{message[:50]}...'"
        )

        # Create a text-specific graph that skips audio processing
        text_workflow = StateGraph(GraphState)

        # Initialize nodes
        intent_analyzer = IntentAnalyzer()
        response_generator = ResponseGenerator()
        tts_node = TTSNode()
        eval_logger = EvalLogger()

        # Add nodes (skip audio_ingestor for text input)
        text_workflow.add_node("intent_analyzer", intent_analyzer)
        text_workflow.add_node("response_generator", response_generator)
        text_workflow.add_node("tts_node", tts_node)
        text_workflow.add_node("eval_logger", eval_logger)

        # Define edges (workflow sequence without audio processing)
        text_workflow.add_edge(START, "intent_analyzer")
        text_workflow.add_edge("intent_analyzer", "response_generator")
        text_workflow.add_edge("response_generator", "tts_node")
        text_workflow.add_edge("tts_node", "eval_logger")
        text_workflow.add_edge("eval_logger", END)

        # Compile and execute the text-specific graph
        text_graph = text_workflow.compile()
        final_state = text_graph.invoke(initial_state)

        logger.info(f"LangGraph text processing completed for session {session_id}")

        return final_state

    def process_audio_to_context(
        self, audio_bytes: bytes, session_id: Optional[str] = None
    ) -> GraphState:
        """Process audio through initial nodes to get context for streaming"""

        if not session_id:
            session_id = str(uuid.uuid4())

        # Initialize state
        initial_state: GraphState = {
            "session_id": session_id,
            "audio_bytes": audio_bytes,
            "transcript": "",
            "user_emotion": EmotionData(label="neutral", confidence=0.0),
            "intent": "",
            "current_mode": MODE_LIGHT,
            "utility_path": UtilityPath.LIGHT.value,
            "router_path": "light",
            "context_memory": {},
            "llm_response": "",
            "memo_context": {"memories": []},
            "response_path": ResponsePath.AGENTIC.value,
            "sophia_emotion": EmotionData(label="neutral", confidence=0.0),
            "is_mock_audio": False,
            "audio_url": "",
            "tts_bytes": b"",
            "evaluation_logs": [],
            "emotion_guidance": [],
            "fallback_used": {},
            "use_voxtral_large": False,
            "cancel_check": None,
        }

        # Process through initial nodes
        audio_ingestor = AudioIngestor()
        intent_analyzer = IntentAnalyzer()

        # Run audio processing and intent analysis
        state = audio_ingestor(initial_state)
        state = intent_analyzer(state)

        return state

    def stream_llm_response(self, state: GraphState):
        """Stream LLM response with context (emotion + memory + RAG)"""
        logger.info(f"Streaming LLM response for session {state['session_id']}")
        _maybe_cancel(state)
        cancel_check = state.get("cancel_check")
        try:
            # Check if we should use Voxtral Large streaming
            if state.get("use_voxtral_large", False):
                from app.services.shared_services import shared_services

                hybrid_service = shared_services.get_hybrid_voxtral_service()

                if hybrid_service:
                    logger.info("Using Voxtral Large streaming")
                    context_dict = self._build_voxtral_context_for_streaming(state)

                    for token_data in hybrid_service.stream_response(
                        state["audio_bytes"],
                        context=context_dict,
                        cancel_check=cancel_check,
                    ):
                        if cancel_check:
                            cancel_check()
                        yield token_data.get("token", "")
                    return

            # Fallback to legacy streaming
            logger.info("Using legacy LLM streaming")

            # Build context like ResponseGenerator does
            response_generator = ResponseGenerator()
            context = response_generator._build_context(state)
            emotion_guidance = _ensure_emotion_guidance(state)

            # Get RAG context for DeFi questions
            rag_context = ""
            if state.get("intent") == "defi_question":
                rag_context = rag_system.get_context_for_llm(
                    state.get("transcript", "")
                )
                logger.info(f"RAG context retrieved: {len(rag_context)} characters")

            # Build comprehensive prompt
            prompt_parts = [
                f"The user seems {state['user_emotion'].label} (confidence: {state['user_emotion'].confidence:.2f})."
            ]

            if context:
                prompt_parts.append(f"Conversation context: {context}")

            guidance_block = format_guidance_block(emotion_guidance)
            if guidance_block:
                prompt_parts.append(guidance_block)

            if rag_context:
                prompt_parts.append(f"Relevant knowledge base:\n{rag_context}")

            prompt_parts.append(f"User question: {state.get('transcript', '')}")

            full_prompt = " | ".join(prompt_parts)
            # Stream response using Mistral LLM
            from app.services.mistral import stream_generate_llm_reply

            for token in stream_generate_llm_reply(
                full_prompt, cancel_check=cancel_check
            ):
                if cancel_check:
                    cancel_check()
                yield token

        except Exception as e:
            logger.error(f"Streaming LLM response failed: {e}")
            _raise_if_cancelled(e)
            # Final fallback
            if (
                "defi" in state.get("transcript", "").lower()
                or "crypto" in state.get("transcript", "").lower()
            ):
                yield "I can help you with DeFi questions. What would you like to know?"
            else:
                yield "I'm here to help. Could you please rephrase your question?"

    def _build_voxtral_context_for_streaming(self, state: GraphState) -> Dict[str, Any]:
        """Build context for Voxtral Large streaming"""
        # Similar to ResponseGenerator._build_voxtral_context but simplified
        memory_context = memory_manager.get_context_for_llm(
            state["session_id"], access_token=state.get("supabase_token")
        )

        context = {
            "intent": state.get("intent", ""),
            "user_emotion": {
                "label": state["user_emotion"].label,
                "confidence": state["user_emotion"].confidence,
            },
        }

        emotion_guidance = _ensure_emotion_guidance(state)
        if emotion_guidance:
            context["emotion_guidance"] = emotion_guidance

        # Add memory context
        if "last_topics" in memory_context:
            context["last_topics"] = memory_context["last_topics"]

        return context
