"""Wrapper service that executes SophiaLangGraph and coordinates evaluation flows."""

import logging
from typing import Dict, Any, Optional
from app.langgraph_nodes import SophiaLangGraph
from app.services.evaluations import evaluation_manager
import threading

logger = logging.getLogger(__name__)


class LangGraphService:
    """Service wrapper for LangGraph integration"""

    def __init__(self):
        self.sophia_graph = SophiaLangGraph()

    def process_conversation(
        self,
        audio_bytes: bytes,
        session_id: str = None,
        collect_evaluation_data: bool = True,
        supabase_token: Optional[str] = None,
        cancel_check=None,
<<<<<<< HEAD
        user_id: Optional[str] = None,
        conversation_count: Optional[int] = None,
=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    ) -> Dict[str, Any]:
        """Process conversation through LangGraph pipeline"""

        logger.info(
            f"Processing conversation through LangGraph for session {session_id}"
        )

        try:
            # Run through LangGraph
            final_state = self.sophia_graph.process_conversation(
                audio_bytes,
                session_id,
                supabase_token=supabase_token,
                cancel_check=cancel_check,
<<<<<<< HEAD
                user_id=user_id,
                conversation_count=conversation_count,
=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
            )

            # Collect evaluation data if requested (instead of running full evaluation)
            if collect_evaluation_data:
                try:
                    evaluation_manager.collect_message_data(
                        session_id=final_state["session_id"],
                        query=final_state["transcript"],
                        answer=final_state["llm_response"],
                        user_audio=final_state["audio_bytes"],
                        sophia_audio=final_state.get("tts_bytes", b""),
                        retrieved_context="",  # Would include RAG context if available
                    )
                    logger.info("Evaluation data collected successfully")
                except Exception as e:
                    logger.error(f"Failed to collect evaluation data: {e}")

            # Check for finished conversations and run evaluations
            try:
                threading.Thread(
                    target=self._run_eval_checks_background,
                    name="eval-check-finished",
                    daemon=True,
                ).start()
            except Exception as e:
                logger.error(f"Failed to start evaluation background task: {e}")

            # Format response
            response = {
                "session_id": final_state["session_id"],
                "transcript": final_state["transcript"],
                "reply": final_state["llm_response"],
                "response_path": final_state.get("response_path"),
<<<<<<< HEAD
                "current_mode": final_state.get("current_mode"),
                "utility_path": final_state.get("utility_path"),
                "router_path": final_state.get("router_path"),
                "had_crisis": final_state.get("had_crisis", False),
                "had_boundary": final_state.get("had_boundary", False),
=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
                "user_emotion": {
                    "label": final_state["user_emotion"].label,
                    "confidence": final_state["user_emotion"].confidence,
                },
                "sophia_emotion": {
                    "label": final_state["sophia_emotion"].label,
                    "confidence": final_state["sophia_emotion"].confidence,
                },
<<<<<<< HEAD
                "is_mock_audio": final_state["is_mock_audio"],
=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
                "audio_url": final_state["audio_url"],
                "intent": final_state["intent"],
                "context_memory": final_state.get("context_memory", {}),
                "fallbacks_used": final_state.get("fallback_used", {}),
                "evaluation_logs": final_state.get("evaluation_logs", []),
                "active_conversations": evaluation_manager.get_active_conversation_count(),
                "conversation_status": evaluation_manager.get_conversation_status(
                    final_state["session_id"]
                ),
            }

            logger.info(
                f"LangGraph conversation processed successfully for session {final_state['session_id']}"
            )
            return response

        except Exception as e:
            logger.error(f"LangGraph conversation processing failed: {e}")
            raise

    def process_text_conversation(
        self,
        message: str,
        session_id: str = None,
        collect_evaluation_data: bool = True,
        supabase_token: Optional[str] = None,
        cancel_check=None,
<<<<<<< HEAD
        user_id: Optional[str] = None,
        conversation_count: Optional[int] = None,
=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    ) -> Dict[str, Any]:
        """Process text-only conversation through LangGraph pipeline"""

        logger.info(
            f"Processing text conversation through LangGraph for session {session_id}"
        )

        try:
            # Run through LangGraph with text input
            final_state = self.sophia_graph.process_text_conversation(
                message,
                session_id,
                supabase_token=supabase_token,
                cancel_check=cancel_check,
<<<<<<< HEAD
                user_id=user_id,
                conversation_count=conversation_count,
=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
            )

            # Collect evaluation data if requested
            if collect_evaluation_data:
                try:
                    evaluation_manager.collect_message_data(
                        session_id=final_state["session_id"],
                        query=final_state["transcript"],
                        answer=final_state["llm_response"],
                        user_audio=b"",  # No audio for text input
                        sophia_audio=final_state.get("tts_bytes", b""),
                        retrieved_context="",  # Would include RAG context if available
                    )
                    logger.info("Evaluation data collected successfully")
                except Exception as e:
                    logger.error(f"Failed to collect evaluation data: {e}")

            # Check for finished conversations and run evaluations
            try:
                finished_reports = (
                    evaluation_manager.check_and_evaluate_finished_conversations()
                )
                if finished_reports:
                    logger.info(
                        f"Completed evaluations for {len(finished_reports)} finished conversations"
                    )
            except Exception as e:
                logger.error(f"Failed to check finished conversations: {e}")

            # Format response
            response = {
                "session_id": final_state["session_id"],
                "transcript": final_state["transcript"],
                "reply": final_state["llm_response"],
                "response_path": final_state.get("response_path"),
<<<<<<< HEAD
                "current_mode": final_state.get("current_mode"),
                "utility_path": final_state.get("utility_path"),
                "router_path": final_state.get("router_path"),
                "had_crisis": final_state.get("had_crisis", False),
                "had_boundary": final_state.get("had_boundary", False),
=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
                "user_emotion": {
                    "label": final_state["user_emotion"].label,
                    "confidence": final_state["user_emotion"].confidence,
                },
                "sophia_emotion": {
                    "label": final_state["sophia_emotion"].label,
                    "confidence": final_state["sophia_emotion"].confidence,
                },
                "audio_url": final_state["audio_url"],
<<<<<<< HEAD
                "is_mock_audio": final_state["is_mock_audio"],
=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
                "intent": final_state["intent"],
                "context_memory": final_state.get("context_memory", {}),
                "fallbacks_used": final_state.get("fallback_used", {}),
                "evaluation_logs": final_state.get("evaluation_logs", []),
                "active_conversations": evaluation_manager.get_active_conversation_count(),
                "conversation_status": evaluation_manager.get_conversation_status(
                    final_state["session_id"]
                ),
            }

            logger.info(
                f"LangGraph text conversation processed successfully for session {final_state['session_id']}"
            )
            return response

        except Exception as e:
            logger.error(f"LangGraph text conversation processing failed: {e}")
            raise

    async def stream_conversation_response(
<<<<<<< HEAD
        self,
        audio_bytes: bytes,
        session_id: str = None,
        supabase_token: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_count: Optional[int] = None,
    ):
        """Stream conversation response through full LangGraph pipeline with all 5 nodes

        M2-BUG-1 Fix: Executes complete LangGraph flow with ALL 5 nodes:
        - AudioIngestor: Voxtral ASR + Phoenix emotion analysis
        - IntentAnalyzer: Intent classification
        - ResponseGenerator: Memory (Mem0) + RAG + emotion-guided prompts
        - TTSNode: Inworld TTS (executed after streaming completes)
        - EvalLogger: Save to Supabase/Mem0 + evaluation logging

        Also includes tier-0 fast classification for immediate UX feedback.
        """

        logger.info(
            f"🎯 M2-BUG-1 FIX: Streaming through FULL LangGraph pipeline (all 5 nodes) for session {session_id}"
        )

        try:
            # Step 1: Quick tier-0 classification for immediate feedback (Task #42537)
            tier0_result = None
            try:
                from app.services.tier0_classifier import classify_tier0_fast
                from app.services.mistral import transcribe_audio_with_voxtral

                # Quick transcription for tier-0
                transcript = transcribe_audio_with_voxtral(audio_bytes)
                logger.info(f"📝 Transcript ({len(transcript)} chars): '{transcript}'")

                # Tier-0 classification (2000ms timeout - increased for better accuracy)
                result = await classify_tier0_fast(
                    transcript, prosody=None, timeout_ms=2000
                )

                logger.info(
                    f"⚡ Tier-0: intent={result.type}, emotion={result.emotion}, "
=======
        self, audio_bytes: bytes, session_id: str = None
    ):
        """Stream conversation response with tier-0 classification - Task #42537"""

        logger.info(
            f"Streaming conversation with tier-0 classifier for session {session_id}"
        )

        try:
            # Step 1: STT to get transcript
            from app.services.mistral import transcribe_audio_with_voxtral

            transcript = transcribe_audio_with_voxtral(audio_bytes)
            logger.info(f"📝 Transcript ({len(transcript)} chars): '{transcript}'")

            # Step 2: Tier-0 Fast Classifier (Task #42537)
            tier0_result = None
            try:
                from app.services.tier0_classifier import classify_tier0_fast

                # Call async function directly with await (now that we're in async generator)
                result = await classify_tier0_fast(
                    transcript, prosody=None, timeout_ms=500
                )

                logger.info(
                    f"🎯 Tier-0: intent={result.type}, emotion={result.emotion}, "
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
                    f"confidence={result.confidence:.2f}, latency={result.latency_ms}ms, "
                    f"source={result.source}"
                )

<<<<<<< HEAD
                # Send tier-0 results to frontend immediately
=======
                # Send tier-0 results to frontend as first yield
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
                tier0_result = {
                    "__tier0__": True,
                    "transcript": transcript,
                    "intent": result.type,
                    "emotion": result.emotion,
                    "confidence": result.confidence,
                    "latency_ms": result.latency_ms,
                    "source": result.source,
                }
                yield tier0_result

                # Check for crisis
                if result.type == "crisis":
                    logger.warning(f"🚨 CRISIS DETECTED in session {session_id}")
                    yield "I'm very concerned about what you're sharing. Please reach out to a crisis helpline immediately. "
                    yield "In the US: 988 (Suicide & Crisis Lifeline). You matter, and help is available 24/7."
                    return

            except Exception as e:
                logger.warning(
<<<<<<< HEAD
                    f"⚠️ Tier-0 classifier failed: {e}, continuing with full pipeline"
                )

            # Step 2: Process through FULL LangGraph pipeline
            # This executes: AudioIngestor → IntentAnalyzer nodes
            logger.info(
                "🔄 Processing through LangGraph nodes (Phoenix emotion, Memory, RAG)..."
            )
            state = self.sophia_graph.process_audio_to_context(
                audio_bytes,
                session_id,
                supabase_token=supabase_token,
                user_id=user_id,
                conversation_count=conversation_count,
            )

            logger.info(
                f"✅ NODE 1-2 completed: "
                f"emotion={state['user_emotion'].label} ({state['user_emotion'].confidence:.2f}), "
                f"intent={state.get('intent')}, "
                f"mode={state.get('current_mode')}"
            )

            # Step 3: Execute NODE 3: ResponseGenerator (via stream_llm_response)
            # Note: stream_llm_response() internally calls ResponseGenerator._build_context()
            # which extracts memory (Flash + Mem0) and RAG context
            logger.info(
                "🔄 NODE 3: ResponseGenerator - Streaming LLM response with memory + RAG + emotion guidance..."
            )
            full_response = ""
            for token in self.sophia_graph.stream_llm_response(state):
                full_response += token
                yield token

            # Update state with full response
            state["llm_response"] = full_response
            logger.info(
                f"✅ NODE 3 completed: LLM response generated ({len(full_response)} chars) "
                f"with memory context (Flash + Mem0) and RAG integration"
            )

            # Step 4: Execute NODE 4: TTSNode (audio synthesis + emotion analysis)
            logger.info(
                "🔄 NODE 4: Executing TTSNode (audio synthesis + emotion analysis)..."
            )
            from app.langgraph_nodes import TTSNode

            tts_node = TTSNode()
            state = tts_node(state)

            logger.info(
                f"✅ NODE 4 completed: audio_url={state.get('audio_url')}, "
                f"sophia_emotion={state['sophia_emotion'].label}({state['sophia_emotion'].confidence:.2f})"
            )

            # Step 5: Execute NODE 5: EvalLogger (save to Supabase/Mem0)
            logger.info(
                "🔄 NODE 5: Executing EvalLogger (saving conversation to Supabase + Mem0)..."
            )
            from app.langgraph_nodes import EvalLogger

            eval_logger = EvalLogger()
            state = eval_logger(state)

            logger.info(
                f"✅ NODE 5 completed: Conversation saved to Supabase/Mem0, "
                f"evaluation logs: {len(state.get('evaluation_logs', []))} entries"
            )

            logger.info(
                f"🎉 FULL 5-node pipeline completed successfully for session {session_id}:\n"
                f"   ✅ AudioIngestor (ASR + emotion)\n"
                f"   ✅ IntentAnalyzer (intent classification)\n"
                f"   ✅ ResponseGenerator (memory retrieval + RAG + LLM response)\n"
                f"   ✅ TTSNode (audio synthesis + emotion analysis)\n"
                f"   ✅ EvalLogger (save to Supabase + Mem0)"
            )

        except Exception as e:
            logger.error(f"❌ LangGraph streaming failed: {e}")
            import traceback

            traceback.print_exc()
            # Fallback to rule-based response
            yield "I'm having trouble processing your request. Could you please try again?"

    def stream_conversation_response_old(
        self,
        audio_bytes: bytes,
        session_id: str = None,
        supabase_token: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_count: Optional[int] = None,
    ):
        """Stream conversation response through LangGraph pipeline

        Flow: Audio → Voxtral ASR → Mistral LLM (streaming)
        """

        logger.info(
            f"Streaming conversation through LangGraph for session {session_id}"
        )

        try:
            # Process audio to get context (ASR + emotion + intent + RAG)
            state = self.sophia_graph.process_audio_to_context(
                audio_bytes,
                session_id,
                supabase_token=supabase_token,
                user_id=user_id,
                conversation_count=conversation_count,
            )

=======
                    f"Tier-0 classifier failed: {e}, continuing without classification"
                )

            # Step 3: Generate response with streaming
            from app.services.mistral import stream_generate_reply_from_audio

            for token in stream_generate_reply_from_audio(audio_bytes):
                yield token

        except Exception as e:
            logger.error(f"Conversation streaming failed: {e}")
            # Fallback to rule-based response
            yield "I'm having trouble processing your request. Could you please try again?"

    def stream_conversation_response_old(self, audio_bytes: bytes, session_id: str = None):
        """Stream conversation response through LangGraph pipeline
        
        Flow: Audio → Voxtral ASR → Mistral LLM (streaming)
        """
        
        logger.info(f"Streaming conversation through LangGraph for session {session_id}")
        
        try:
            # Process audio to get context (ASR + emotion + intent + RAG)
            state = self.sophia_graph.process_audio_to_context(audio_bytes, session_id)
            
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
            # Stream LLM response using the processed context
            for token in self.sophia_graph.stream_llm_response(state):
                yield token

        except Exception as e:
            logger.error(f"LangGraph streaming failed: {e}")
            yield "I'm having trouble processing your request. Could you please try again?"

    def _run_eval_checks_background(self):
        """Run evaluation checks in background thread"""
        try:
            evaluation_manager.check_and_run_evaluations()
        except Exception as e:
            logger.error(f"Background evaluation check failed: {e}")


# Singleton instance
langgraph_service = LangGraphService()
