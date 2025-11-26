"""Conversation evaluation toolkit for RAGAS scoring, Phoenix drift monitoring, and reports."""

import json
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from app.config import get_settings
from app.services.supabase import get_supabase
from app.services.emotion import analyze_emotion_audio

logger = logging.getLogger(__name__)


@dataclass
class RAGASMetrics:
    faithfulness: float
    relevance: float
    correctness: float
    average_score: float


@dataclass
class PhoenixMetrics:
    emotion_label: str
    confidence: float
    session_id: str
    timestamp: float
    role: str  # "user" or "sophia"


@dataclass
class ConversationData:
    """Data collected during a conversation for later evaluation"""

    session_id: str
    messages: List[Dict[str, Any]]
    audio_data: List[Dict[str, bytes]]
    created_at: float
    last_activity: float


@dataclass
class EvaluationReport:
    session_id: str
    ragas_metrics: Optional[RAGASMetrics]
    phoenix_metrics: List[PhoenixMetrics]
    drift_alert: bool
    baseline_confidence: float
    current_confidence: float
    timestamp: float
    total_messages: int
    conversation_duration: float


class RAGASEvaluator:
    """RAGAS evaluation for answer quality"""

    def __init__(self):
        self.settings = get_settings()
        self.ground_truth_qa = self._get_ground_truth_qa()

    def _get_ground_truth_qa(self) -> List[Dict[str, str]]:
        """Ground truth Q&A pairs for evaluation"""
        return [
            {
                "query": "What is DeFi?",
                "expected_answer": "DeFi refers to decentralized financial services built on blockchain technology without traditional intermediaries",
                "context": "DeFi basics and definition",
            },
            {
                "query": "What are the risks of yield farming?",
                "expected_answer": "Yield farming risks include impermanent loss, smart contract bugs, market volatility, and protocol risks",
                "context": "DeFi risks and yield farming",
            },
            {
                "query": "How does staking work?",
                "expected_answer": "Staking involves locking cryptocurrency to support network operations and earn rewards",
                "context": "Staking mechanism and rewards",
            },
            {
                "query": "What is impermanent loss?",
                "expected_answer": "Impermanent loss occurs when providing liquidity and token price ratios change unfavorably",
                "context": "Liquidity provision risks",
            },
            {
                "query": "How do I choose a safe DeFi protocol?",
                "expected_answer": "Look for audited contracts, high TVL, established teams, and transparent tokenomics",
                "context": "DeFi protocol evaluation criteria",
            },
            {
                "query": "What is TVL in DeFi?",
                "expected_answer": "TVL is Total Value Locked, representing assets deposited in a DeFi protocol",
                "context": "DeFi metrics and indicators",
            },
            {
                "query": "What are governance tokens?",
                "expected_answer": "Governance tokens provide voting rights in protocol decisions and management",
                "context": "DeFi governance and tokenomics",
            },
            {
                "query": "What is slippage in trading?",
                "expected_answer": "Slippage is price difference between trade placement and execution due to market movement",
                "context": "DEX trading mechanics",
            },
            {
                "query": "How do flash loans work?",
                "expected_answer": "Flash loans allow borrowing without collateral if repaid within the same transaction",
                "context": "Advanced DeFi mechanisms",
            },
            {
                "query": "What are stablecoins?",
                "expected_answer": "Stablecoins are cryptocurrencies designed to maintain stable value, usually pegged to USD",
                "context": "Cryptocurrency basics and stablecoins",
            },
        ]

    def evaluate_response(
        self, query: str, answer: str, retrieved_context: str = ""
    ) -> RAGASMetrics:
        """Evaluate response quality using RAGAS-inspired metrics"""
        try:
            # Simplified RAGAS evaluation (in production, would use actual RAGAS library)
            faithfulness = self._calculate_faithfulness(answer, retrieved_context)
            relevance = self._calculate_relevance(query, answer)
            correctness = self._calculate_correctness(query, answer)

            average_score = (faithfulness + relevance + correctness) / 3

            return RAGASMetrics(
                faithfulness=faithfulness,
                relevance=relevance,
                correctness=correctness,
                average_score=average_score,
            )

        except Exception as e:
            logger.error(f"RAGAS evaluation failed: {e}")
            return RAGASMetrics(0.0, 0.0, 0.0, 0.0)

    def _calculate_faithfulness(self, answer: str, context: str) -> float:
        """Calculate how faithful the answer is to the retrieved context"""
        if not context:
            return 0.7  # Neutral score if no context

        # Simple keyword overlap for demonstration
        answer_words = set(answer.lower().split())
        context_words = set(context.lower().split())

        if len(answer_words) == 0:
            return 0.0

        overlap = len(answer_words.intersection(context_words))
        faithfulness = min(overlap / len(answer_words), 1.0)

        # Add base score to avoid too low scores
        return max(faithfulness, 0.3)

    def _calculate_relevance(self, query: str, answer: str) -> float:
        """Calculate how relevant the answer is to the query"""
        query_words = set(query.lower().split())
        answer_words = set(answer.lower().split())

        if len(query_words) == 0 or len(answer_words) == 0:
            return 0.0

        overlap = len(query_words.intersection(answer_words))
        relevance = min(overlap / len(query_words), 1.0)

        # Boost score if answer contains key terms
        key_terms = ["defi", "yield", "staking", "protocol", "token", "blockchain"]
        if any(term in answer.lower() for term in key_terms):
            relevance += 0.2

        return min(relevance, 1.0)

    def _calculate_correctness(self, query: str, answer: str) -> float:
        """Calculate correctness against ground truth"""
        # Find matching ground truth
        ground_truth = None
        for qa in self.ground_truth_qa:
            if self._queries_similar(query, qa["query"]):
                ground_truth = qa["expected_answer"]
                break

        if not ground_truth:
            return 0.6  # Neutral score if no ground truth found

        # Simple similarity based on word overlap
        truth_words = set(ground_truth.lower().split())
        answer_words = set(answer.lower().split())

        if len(truth_words) == 0:
            return 0.0

        overlap = len(truth_words.intersection(answer_words))
        correctness = overlap / len(truth_words)

        return min(correctness, 1.0)

    def _queries_similar(self, q1: str, q2: str) -> bool:
        """Check if two queries are similar"""
        q1_words = set(q1.lower().split())
        q2_words = set(q2.lower().split())

        overlap = len(q1_words.intersection(q2_words))
        similarity = overlap / max(len(q1_words), len(q2_words))

        return similarity > 0.5


class PhoenixDriftMonitor:
    """Monitor emotion drift using Phoenix evaluations"""

    def __init__(self):
        self.settings = get_settings()
        self.supabase = get_supabase()
        self.baseline_confidence = 0.81  # From milestone 1
        self.drift_threshold = 0.20  # 20% drop threshold

    def evaluate_audio_emotion(
        self, audio_bytes: bytes, session_id: str, role: str
    ) -> PhoenixMetrics:
        """Evaluate emotion from audio using Phoenix"""
        try:
            emotion_result = analyze_emotion_audio(audio_bytes)

            metrics = PhoenixMetrics(
                emotion_label=emotion_result.label,
                confidence=emotion_result.confidence,
                session_id=session_id,
                timestamp=time.time(),
                role=role,
            )

            logger.info(
                f"Phoenix evaluation: {role} emotion={emotion_result.label} "
                f"confidence={emotion_result.confidence:.2f}"
            )

            return metrics

        except Exception as e:
            logger.error(f"Phoenix evaluation failed: {e}")
            return PhoenixMetrics("neutral", 0.5, session_id, time.time(), role)

    def check_drift_alert(
        self, recent_metrics: List[PhoenixMetrics]
    ) -> Tuple[bool, float]:
        """Check if emotion confidence has drifted below threshold"""
        if not recent_metrics:
            return False, self.baseline_confidence

        # Calculate average confidence from recent metrics
        sophia_confidences = [
            m.confidence for m in recent_metrics if m.role == "sophia"
        ]

        if not sophia_confidences:
            return False, self.baseline_confidence

        current_confidence = np.mean(sophia_confidences)

        # Check if drop exceeds threshold
        confidence_drop = (
            self.baseline_confidence - current_confidence
        ) / self.baseline_confidence
        drift_alert = confidence_drop > self.drift_threshold

        if drift_alert:
            logger.warning(
                f"DRIFT ALERT: Confidence dropped from {self.baseline_confidence:.2f} "
                f"to {current_confidence:.2f} ({confidence_drop:.1%} drop)"
            )

        return drift_alert, current_confidence

    def get_recent_metrics(self, limit: int = 10) -> List[PhoenixMetrics]:
        """Get recent Phoenix metrics from storage"""
        try:
            # In a real implementation, this would query stored metrics
            # For now, return empty list
            logger.info(f"Would retrieve last {limit} Phoenix metrics from storage")
            return []

        except Exception as e:
            logger.error(f"Failed to retrieve Phoenix metrics: {e}")
            return []


class EvaluationManager:
    """Main evaluation orchestrator"""

    def __init__(self):
        self.ragas_evaluator = RAGASEvaluator()
        self.phoenix_monitor = PhoenixDriftMonitor()
        self.supabase = get_supabase()
        self.active_conversations: Dict[str, ConversationData] = {}
        self.conversation_timeout = 300  # 5 minutes of inactivity ends conversation

    def collect_message_data(
        self,
        session_id: str,
        query: str,
        answer: str,
        user_audio: bytes,
        sophia_audio: bytes,
        retrieved_context: str = "",
    ) -> None:
        """Collect data from a message exchange for later evaluation"""

        current_time = time.time()

        # Initialize conversation data if new session
        if session_id not in self.active_conversations:
            self.active_conversations[session_id] = ConversationData(
                session_id=session_id,
                messages=[],
                audio_data=[],
                created_at=current_time,
                last_activity=current_time,
            )
            logger.info(f"Started collecting data for new conversation: {session_id}")

        # Add message data
        conversation = self.active_conversations[session_id]
        conversation.messages.append(
            {
                "query": query,
                "answer": answer,
                "retrieved_context": retrieved_context,
                "timestamp": current_time,
            }
        )

        # Add audio data
        conversation.audio_data.append(
            {
                "user_audio": user_audio,
                "sophia_audio": sophia_audio,
                "timestamp": current_time,
            }
        )

        # Update last activity
        conversation.last_activity = current_time

        logger.info(
            f"Collected message data for session {session_id}. Total messages: {len(conversation.messages)}"
        )

    def check_and_evaluate_finished_conversations(self) -> List[EvaluationReport]:
        """Check for finished conversations and run evaluations"""

        current_time = time.time()
        finished_sessions = []
        reports = []

        # Find conversations that have timed out
        for session_id, conversation in self.active_conversations.items():
            if current_time - conversation.last_activity > self.conversation_timeout:
                finished_sessions.append(session_id)

        # Evaluate finished conversations
        for session_id in finished_sessions:
            try:
                report = self._evaluate_finished_conversation(session_id)
                reports.append(report)
                # Remove from active conversations
                del self.active_conversations[session_id]
                logger.info(
                    f"Completed evaluation for finished conversation: {session_id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to evaluate finished conversation {session_id}: {e}"
                )

        return reports
<<<<<<< HEAD

    def check_and_run_evaluations(self) -> List[EvaluationReport]:
        """Alias for check_and_evaluate_finished_conversations"""
        return self.check_and_evaluate_finished_conversations()

    def force_evaluate_conversation(
        self, session_id: str
    ) -> Optional[EvaluationReport]:
=======
    
    def check_and_run_evaluations(self) -> List[EvaluationReport]:
        """Alias for check_and_evaluate_finished_conversations"""
        return self.check_and_evaluate_finished_conversations()
    
    def force_evaluate_conversation(self, session_id: str) -> Optional[EvaluationReport]:
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        """Force evaluation of a specific conversation (e.g., when user explicitly ends it)"""

        if session_id not in self.active_conversations:
            logger.warning(f"No active conversation found for session {session_id}")
            return None

        try:
            report = self._evaluate_finished_conversation(session_id)
            del self.active_conversations[session_id]
            logger.info(f"Force completed evaluation for conversation: {session_id}")
            return report
        except Exception as e:
            logger.error(f"Failed to force evaluate conversation {session_id}: {e}")
            return None

    def _evaluate_finished_conversation(self, session_id: str) -> EvaluationReport:
        """Evaluate a finished conversation using all collected data"""

        conversation = self.active_conversations[session_id]
        current_time = time.time()

        logger.info(
            f"Evaluating finished conversation {session_id} with {len(conversation.messages)} messages"
        )

        # Aggregate RAGAS evaluation across all messages
        ragas_metrics = None
        try:
            all_ragas_scores = []
            for msg in conversation.messages:
                msg_ragas = self.ragas_evaluator.evaluate_response(
                    msg["query"], msg["answer"], msg["retrieved_context"]
                )
                all_ragas_scores.append(msg_ragas)

            if all_ragas_scores:
                # Calculate average metrics across all messages
                avg_faithfulness = np.mean([r.faithfulness for r in all_ragas_scores])
                avg_relevance = np.mean([r.relevance for r in all_ragas_scores])
                avg_correctness = np.mean([r.correctness for r in all_ragas_scores])
                avg_score = (avg_faithfulness + avg_relevance + avg_correctness) / 3

                ragas_metrics = RAGASMetrics(
                    faithfulness=avg_faithfulness,
                    relevance=avg_relevance,
                    correctness=avg_correctness,
                    average_score=avg_score,
                )
                logger.info(
                    f"Aggregated RAGAS metrics: avg={avg_score:.2f} across {len(all_ragas_scores)} messages"
                )
        except Exception as e:
            logger.error(f"RAGAS evaluation failed: {e}")

        # Phoenix evaluations for all audio data
        phoenix_metrics = []
        try:
            for i, audio_data in enumerate(conversation.audio_data):
                user_metrics = self.phoenix_monitor.evaluate_audio_emotion(
                    audio_data["user_audio"], session_id, "user"
                )
                user_metrics.timestamp = audio_data["timestamp"]

                sophia_metrics = self.phoenix_monitor.evaluate_audio_emotion(
                    audio_data["sophia_audio"], session_id, "sophia"
                )
                sophia_metrics.timestamp = audio_data["timestamp"]

                phoenix_metrics.extend([user_metrics, sophia_metrics])

            logger.info(
                f"Phoenix evaluation completed for {len(phoenix_metrics)} audio samples"
            )
        except Exception as e:
            logger.error(f"Phoenix evaluation failed: {e}")

        # Drift monitoring using all Phoenix metrics
        drift_alert = False
        current_confidence = self.phoenix_monitor.baseline_confidence
        try:
            drift_alert, current_confidence = self.phoenix_monitor.check_drift_alert(
                phoenix_metrics
            )
        except Exception as e:
            logger.error(f"Drift monitoring failed: {e}")

        # Calculate conversation duration
        conversation_duration = conversation.last_activity - conversation.created_at

        # Create evaluation report
        report = EvaluationReport(
            session_id=session_id,
            ragas_metrics=ragas_metrics,
            phoenix_metrics=phoenix_metrics,
            drift_alert=drift_alert,
            baseline_confidence=self.phoenix_monitor.baseline_confidence,
            current_confidence=current_confidence,
            timestamp=current_time,
            total_messages=len(conversation.messages),
            conversation_duration=conversation_duration,
        )

        # Log evaluation summary
        self._log_evaluation_summary(report)

        return report

    def _log_evaluation_summary(self, report: EvaluationReport):
        """Log comprehensive evaluation summary"""

        # Calculate emotion distribution
        user_emotions = [
            m.emotion_label for m in report.phoenix_metrics if m.role == "user"
        ]
        sophia_emotions = [
            m.emotion_label for m in report.phoenix_metrics if m.role == "sophia"
        ]

        summary = {
            "session_id": report.session_id,
            "total_messages": report.total_messages,
            "conversation_duration_minutes": round(
                report.conversation_duration / 60, 2
            ),
            "ragas_average": report.ragas_metrics.average_score
            if report.ragas_metrics
            else "N/A",
            "user_emotions": list(set(user_emotions)) if user_emotions else ["N/A"],
            "sophia_emotions": list(set(sophia_emotions))
            if sophia_emotions
            else ["N/A"],
            "total_phoenix_evaluations": len(report.phoenix_metrics),
            "drift_alert": report.drift_alert,
            "confidence_drop": f"{report.baseline_confidence:.2f} -> {report.current_confidence:.2f}",
        }

        logger.info(f"Conversation Evaluation Summary: {json.dumps(summary, indent=2)}")

    def get_active_conversation_count(self) -> int:
        """Get number of active conversations being tracked"""
        return len(self.active_conversations)

    def get_conversation_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific conversation"""
        if session_id not in self.active_conversations:
            return None

        conversation = self.active_conversations[session_id]
        current_time = time.time()

        return {
            "session_id": session_id,
            "message_count": len(conversation.messages),
            "duration_minutes": round((current_time - conversation.created_at) / 60, 2),
            "last_activity_minutes_ago": round(
                (current_time - conversation.last_activity) / 60, 2
            ),
            "will_timeout_in_minutes": round(
                (
                    self.conversation_timeout
                    - (current_time - conversation.last_activity)
                )
                / 60,
                2,
            ),
        }

    def run_batch_evaluation(self, num_queries: int = 10) -> Dict[str, Any]:
        """Run batch evaluation on ground truth queries"""
        logger.info(f"Running batch evaluation with {num_queries} queries")

        results = []
        ground_truth_qa = self.ragas_evaluator.ground_truth_qa[:num_queries]

        for qa in ground_truth_qa:
            # Simulate generating an answer (in production, would call actual system)
            simulated_answer = (
                f"Based on DeFi knowledge: {qa['expected_answer'][:30]}..."
            )

            ragas_metrics = self.ragas_evaluator.evaluate_response(
                qa["query"], simulated_answer, qa["context"]
            )

            results.append(
                {
                    "query": qa["query"],
                    "ragas_score": ragas_metrics.average_score,
                    "faithfulness": ragas_metrics.faithfulness,
                    "relevance": ragas_metrics.relevance,
                    "correctness": ragas_metrics.correctness,
                }
            )

        # Calculate overall metrics
        avg_score = np.mean([r["ragas_score"] for r in results])
        target_met = avg_score >= 0.75

        batch_results = {
            "total_queries": len(results),
            "average_score": avg_score,
            "target_score": 0.75,
            "target_met": target_met,
            "results": results,
            "timestamp": time.time(),
        }

        logger.info(
            f"Batch evaluation completed: avg_score={avg_score:.2f}, target_met={target_met}"
        )

        return batch_results


# Singleton instances
evaluation_manager = EvaluationManager()
