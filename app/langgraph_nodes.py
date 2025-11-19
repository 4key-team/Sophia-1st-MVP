"""LangGraph state machine defining audio ingestion, intent analysis, response, and TTS nodes."""

import asyncio
import logging
import time
import uuid
from typing import Callable, Dict, Any, Optional, List, TypedDict
from dataclasses import dataclass

from langgraph.graph import StateGraph, START, END

from app.services.mistral import (
    transcribe_audio_with_voxtral,
    generate_llm_reply,
)
from app.services.emotion import analyze_emotion_audio, infer_text_emotion
from app.services.tts import synthesize_inworld
from app.services.supabase import upload_audio_and_get_url
from app.services.memory import memory_manager, ConversationTurn
from app.services.rag import rag_system
from app.services.memo import mem0_client  # Task #42597
from app.services.prompt_composer import prompt_composer  # Task #42597
from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class EmotionData:
    label: str
    confidence: float


CancelCallback = Callable[[], None]


class GraphState(TypedDict):
    session_id: str
    audio_bytes: bytes
    transcript: str
    user_emotion: EmotionData
    intent: str
    context_memory: Dict[str, Any]
    mem0_context: Dict[str, Any]  # Task #42597: Mem0 intelligent memory context
    llm_response: str
    sophia_emotion: EmotionData
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
                state["audio_bytes"],
                cancel_check=state.get("cancel_check"),
            )
            user_emotion = analyze_emotion_audio(state["audio_bytes"])

            state["transcript"] = transcript
            state["user_emotion"] = EmotionData(
                label=user_emotion.label, confidence=user_emotion.confidence
            )

            logger.info(
                f"AudioIngestor (legacy) completed: transcript='{transcript[:50]}...', "
                f"emotion={user_emotion.label}({user_emotion.confidence:.2f})"
            )

        except Exception as e:
            logger.error(f"AudioIngestor failed: {e}")
            _raise_if_cancelled(e)
            # Set fallback flag and try Whisper fallback
            state["fallback_used"]["stt"] = "whisper_fallback"
            _maybe_cancel(state)
            state["transcript"] = self._whisper_fallback(state, state["audio_bytes"])
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
    """Classifies user intent (DeFi question, emotional support, small talk)"""

    def __call__(self, state: GraphState) -> GraphState:
        logger.info(f"IntentAnalyzer processing session {state['session_id']}")

        transcript = state["transcript"]

        # Simple rule-based intent classification
        intent = self._classify_intent(transcript)
        state["intent"] = intent

        logger.info(f"IntentAnalyzer completed: intent={intent}")
        return state

    def _classify_intent(self, text: str) -> str:
        """Simple intent classification"""
        text_lower = text.lower()

        defi_keywords = [
            "defi",
            "yield",
            "staking",
            "liquidity",
            "farming",
            "token",
            "swap",
            "protocol",
            "apy",
            "apr",
            "pool",
            "vault",
            "ethereum",
        ]

        emotional_keywords = [
            "sad",
            "worried",
            "anxious",
            "happy",
            "excited",
            "confused",
            "frustrated",
            "help me",
        ]

        if any(keyword in text_lower for keyword in defi_keywords):
            return "defi_question"
        elif any(keyword in text_lower for keyword in emotional_keywords):
            return "emotional_support"
        else:
            return "small_talk"


class ResponseGenerator:
    """Generates responses using appropriate pipeline based on AudioIngestor decision"""

    def __init__(self, use_voxtral_large: bool = True):
        self.settings = get_settings()
        self.use_voxtral_large = use_voxtral_large
        logger.info(
            f"ResponseGenerator initialized (Voxtral Large preference: {use_voxtral_large})"
        )

    def __call__(self, state: GraphState) -> GraphState:
        logger.info(f"ResponseGenerator processing session {state['session_id']}")
        state.setdefault("fallback_used", {})
        _maybe_cancel(state)

        # Check pipeline decision from AudioIngestor
        use_voxtral_large = state.get("use_voxtral_large", False)

        try:
            if use_voxtral_large:
                # VOXTRAL LARGE PATH: Complete processing
                return self._process_with_voxtral_large(state)
            else:
                # LEGACY PATH: LLM-only processing
                return self._process_with_legacy_llm(state)

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

    def _process_with_voxtral_large(self, state: GraphState) -> GraphState:
        """Process using Voxtral Large unified pipeline (transcript already extracted by AudioIngestor)"""
        from app.services.shared_services import shared_services

        logger.info("ResponseGenerator: Processing with Voxtral Large")
        cancel_check = state.get("cancel_check")

        try:
            hybrid_service = shared_services.get_hybrid_voxtral_service()
            if not hybrid_service:
                raise Exception("Shared HybridVoxtralService not available")

            # Build context for Voxtral Large (transcript already available from AudioIngestor)
            context_dict = self._build_voxtral_context(state)

            # Use Voxtral Large for response generation with built-in fallback logic
            # Build a comprehensive system prompt using existing transcript and context (Task #42597: with Mem0)
            system_prompt = self._build_voxtral_system_prompt(
                intent=state.get("intent", ""),
                mem0_context=state.get("mem0_context"),
                user_emotion=state["user_emotion"].label
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

        context = self._build_context(state)
        emotion_guidance = _ensure_emotion_guidance(state)
        response = self._generate_with_context(
            state.get("transcript", ""),
            state.get("intent", ""),
            state["user_emotion"],
            context,
            emotion_guidance,
            cancel_check=cancel_check,
        )
        state["llm_response"] = response

        logger.info(
            f"ResponseGenerator (legacy) completed: response='{state['llm_response'][:50]}...'"
        )
        return state

    def _build_voxtral_context(self, state: GraphState) -> Dict[str, Any]:
        """Build rich context dictionary for Voxtral Large"""
        # Get memory context
        memory_context = memory_manager.get_context_for_llm(
            state["session_id"], access_token=state.get("supabase_token")
        )
        state["context_memory"] = memory_context

        # Task #42597: Get Mem0 intelligent memory
        mem0_memories = []
        try:
            # Extract user_id from session (assuming session_id format or use default)
            user_id = state.get("user_id", state["session_id"])
            mem0_memories = asyncio.run(
                mem0_client.search_memories(
                    user_id=user_id,
                    query_text=state["transcript"],
                    top_k=3
                )
            )
            if mem0_memories:
                logger.info(f"Mem0: Retrieved {len(mem0_memories)} relevant memories")
        except Exception as e:
            logger.warning(f"Mem0 memory retrieval failed: {e}")

        state["mem0_context"] = {"memories": mem0_memories}

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
        # Get context from memory manager
        context = memory_manager.get_context_for_llm(
            state["session_id"], access_token=state.get("supabase_token")
        )
        state["context_memory"] = context

        # Task #42597: Get Mem0 intelligent memory (also for legacy path)
        mem0_memories = []
        try:
            user_id = state.get("user_id", state["session_id"])
            mem0_memories = asyncio.run(
                mem0_client.search_memories(
                    user_id=user_id,
                    query_text=state.get("transcript", ""),
                    top_k=3
                )
            )
            if mem0_memories:
                logger.info(f"Mem0 (legacy): Retrieved {len(mem0_memories)} memories")
        except Exception as e:
            logger.warning(f"Mem0 memory retrieval (legacy) failed: {e}")

        state["mem0_context"] = {"memories": mem0_memories}

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
        if memo_memories:
            memo_texts = [m.get("memory_text", "") for m in memo_memories[:2]]  # Top 2
            if memo_texts:
                context_parts.append(f"User memories: {'; '.join(memo_texts)}")

        return " | ".join(context_parts) if context_parts else ""

    def _build_voxtral_system_prompt(self, intent: str, mem0_context: Dict[str, Any] = None, user_emotion: str = None) -> str:
        """Build system prompt for Voxtral Large based on intent using PromptComposer (Task #42597)"""
        # Use PromptComposer to build dynamic prompt with memory context
        system_prompt = prompt_composer.compose_system_prompt(
            memory_context=mem0_context,
            user_emotion=user_emotion
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

    def _generate_with_context(
        self,
        transcript: str,
        intent: str,
        user_emotion: EmotionData,
        context: str,
        emotion_guidance: List[str],
        *,
        cancel_check: Optional[CancelCallback] = None,
    ) -> str:
        """Generate response with context and emotion awareness"""
        if cancel_check:
            cancel_check()
        # Get RAG context for DeFi questions
        rag_context = ""
        if intent == "defi_question":
            rag_context = rag_system.get_context_for_llm(transcript)
            logger.info(f"RAG context retrieved: {len(rag_context)} characters")

        # Enhanced prompt based on intent and emotion
        # if intent == "defi_question":
        #    system_prompt = "You are Sophia, a knowledgeable DeFi mentor. Use the provided FAQ context to give accurate, educational responses about DeFi concepts. Keep responses under 50 words."
        # elif intent == "emotional_support":
        #    system_prompt = "You are Sophia, an empathetic AI companion. Provide supportive and encouraging responses. Keep responses under 50 words."
        # else:
        #    system_prompt = "You are Sophia, a friendly AI assistant. Engage in casual conversation. Keep responses under 50 words."

        # Build comprehensive prompt
        prompt_parts = [
            f"The user seems {user_emotion.label} (confidence: {user_emotion.confidence:.2f})."
        ]

        if context:
            prompt_parts.append(f"Conversation context: {context}")

        guidance_block = format_guidance_block(emotion_guidance)
        if guidance_block:
            prompt_parts.append(guidance_block)
            logger.info(
                "Legacy system prompt guidance applied: %s%s",
                "; ".join(emotion_guidance[:2]),
                "..." if len(emotion_guidance) > 2 else "",
            )

        if rag_context:
            prompt_parts.append(f"Relevant knowledge base:\n{rag_context}")

        prompt_parts.append(f"User question: {transcript}")

        full_prompt = " | ".join(prompt_parts)

        if cancel_check:
            cancel_check()
        return generate_llm_reply(full_prompt, cancel_check=cancel_check)

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
            tts_bytes = synthesize_inworld(
                state["llm_response"],
                cancel_check=state.get("cancel_check"),
            )

            # Upload and get URL
            file_name = f"sophia_{int(time.time() * 1000)}_{state['session_id']}.mp3"
            audio_url = upload_audio_and_get_url(
                file_bytes=tts_bytes, file_name=file_name
            )

            # Analyze Sophia's emotion from TTS output
            sophia_emotion = analyze_emotion_audio(tts_bytes)

            state["tts_bytes"] = tts_bytes
            state["audio_url"] = audio_url
            state["sophia_emotion"] = EmotionData(
                label=sophia_emotion.label, confidence=sophia_emotion.confidence
            )

            logger.info(
                f"TTSNode completed: audio_url={audio_url}, "
                f"sophia_emotion={sophia_emotion.label}({sophia_emotion.confidence:.2f})"
            )

        except Exception as e:
            logger.error(f"TTSNode Inworld failed: {e}")
            _raise_if_cancelled(e)
            _maybe_cancel(state)
            # Fallback to Boson AI or other TTS service
            state["fallback_used"]["tts"] = "boson_fallback"
            try:
                tts_bytes = self._boson_ai_fallback(
                    state["llm_response"],
                    cancel_check=state.get("cancel_check"),
                )
                file_name = f"sophia_fallback_{int(time.time() * 1000)}_{state['session_id']}.mp3"
                audio_url = upload_audio_and_get_url(
                    file_bytes=tts_bytes, file_name=file_name
                )
                sophia_emotion = analyze_emotion_audio(tts_bytes)

                state["tts_bytes"] = tts_bytes
                state["audio_url"] = audio_url
                state["sophia_emotion"] = EmotionData(
                    label=sophia_emotion.label, confidence=sophia_emotion.confidence
                )
            except Exception as fallback_error:
                logger.error(f"TTS fallback also failed: {fallback_error}")
                _raise_if_cancelled(fallback_error)
                # Final fallback - empty audio
                state["audio_url"] = ""
                state["sophia_emotion"] = EmotionData(label="neutral", confidence=0.5)

        return state

    def _boson_ai_fallback(
        self,
        text: str,
        cancel_check: Optional[CancelCallback] = None,
    ) -> bytes:
        """Fallback TTS using Boson AI or OpenAI TTS"""
        try:
            if cancel_check:
                cancel_check()
            # Try OpenAI TTS as fallback
            import openai

            client = openai.OpenAI(api_key=get_settings().OPENAI_API_KEY)

            response = client.audio.speech.create(
                model="tts-1", voice="alloy", input=text, response_format="mp3"
            )
            if cancel_check:
                cancel_check()
            return response.content

        except Exception as e:
            logger.error(f"Boson AI fallback failed: {e}")
            # Return empty bytes as final fallback
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
            asyncio.run(self._extract_and_store_memories(
                user_id=user_id,
                session_id=state["session_id"],
                transcript=state["transcript"],
                response=state["llm_response"],
                intent=state["intent"],
                user_emotion=state["user_emotion"].label
            ))
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
        user_emotion: str
    ):
        """Extract and store important memories from conversation (Task #42597)"""
        memories_to_store = []

        # Extract preferences from transcript
        preference_keywords = ["i prefer", "i like", "i love", "i want", "i need", "my favorite"]
        if any(keyword in transcript.lower() for keyword in preference_keywords):
            memories_to_store.append({
                "text": transcript,
                "type": "preference",
                "importance": 0.8
            })

        # Extract emotional patterns
        if user_emotion in ["excited", "happy", "sad", "anxious", "angry"]:
            if len(transcript) > 20:  # Only store meaningful emotional context
                memories_to_store.append({
                    "text": f"User expressed {user_emotion} emotion: {transcript}",
                    "type": "emotion",
                    "importance": 0.6
                })

        # Extract factual information (names, projects, important context)
        fact_keywords = ["i am", "i'm", "my name is", "i work", "i study", "i'm working on"]
        if any(keyword in transcript.lower() for keyword in fact_keywords):
            memories_to_store.append({
                "text": transcript,
                "type": "fact",
                "importance": 0.9
            })

        # Store all extracted memories
        for memory in memories_to_store:
            try:
                await mem0_client.store_memory(
                    user_id=user_id,
                    session_id=session_id,
                    memory_text=memory["text"],
                    memory_type=memory["type"],
                    importance=memory["importance"]
                )
                logger.info(f"Mem0: Stored {memory['type']} memory for user {user_id}")
            except Exception as e:
                logger.warning(f"Failed to store {memory['type']} memory: {e}")


class SophiaLangGraph:
    """Main LangGraph orchestrator"""

    def __init__(self):
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine"""

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

        # Define edges (workflow sequence)
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
            "context_memory": {},
            "llm_response": "",
            "sophia_emotion": EmotionData(label="neutral", confidence=0.0),
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
            "context_memory": {},
            "llm_response": "",
            "sophia_emotion": EmotionData(label="neutral", confidence=0.0),
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
            "context_memory": {},
            "llm_response": "",
            "sophia_emotion": EmotionData(label="neutral", confidence=0.0),
            "audio_url": "",
            "tts_bytes": b"",
            "evaluation_logs": [],
            "emotion_guidance": [],
            "fallback_used": {},
        }

        # Process through initial nodes
        audio_ingestor = AudioIngestor()
        intent_analyzer = IntentAnalyzer()

        # Run audio processing and intent analysis
        state = audio_ingestor(initial_state)
        state = intent_analyzer(state)

        return state

    def stream_llm_response(self, state: GraphState):
        """Stream LLM response using appropriate pipeline"""
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

            # Stream response using legacy pipeline
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
