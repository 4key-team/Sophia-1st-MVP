"""Emotion classification utilities powered by Phoenix and fallback LLM heuristics."""

# ========================================
# CRITICAL: Apply nest_asyncio FIRST - before ANY other imports
# ========================================
try:
    import nest_asyncio

    nest_asyncio.apply()
    _NEST_ASYNC_APPLIED = True
except Exception:  # pragma: no cover - diagnostic only
    _NEST_ASYNC_APPLIED = False

# ========================================
# NOW import everything else
# ========================================
import asyncio
import logging
<<<<<<< HEAD
=======
import sys
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from app.config import get_settings
from app.services.memory import memory_manager

logger = logging.getLogger("emotion")
_DEEP_EMOTION_RAILS = [
    "joy",
    "excited",
    "sad",
    "anxious",
    "grief",
    "panic",
    "anger",
    "fearful",
    "calm",
    "neutral",
    "hopeful",
    "lonely",
]

# Log nest_asyncio status AFTER logger is ready
if _NEST_ASYNC_APPLIED:
    logger.info("✅ nest_asyncio applied successfully at module import")
else:
    logger.warning("⚠️ nest_asyncio not available - emotion analysis may fail")


class Emotion(BaseModel):
    label: str
    confidence: float


@dataclass
class PhoenixBackgroundMetrics:
    phoenix_bg_success_total: int = 0
    phoenix_bg_failure_total: int = 0
    phoenix_bg_p95_latency_ms: float = 0.0


class _PhoenixBackgroundExecutor:
    """Runs Phoenix deep classification in a background asyncio loop."""

    def __init__(self):
        self.settings = get_settings()
        self.timeout_seconds = getattr(
            self.settings, "PHOENIX_BG_TIMEOUT_SECONDS", 12.0
        )
        self.metrics = PhoenixBackgroundMetrics()
        self._latencies: List[float] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def submit(self, session_id: str, transcript: str, prosody_present: bool) -> None:
        """Schedule background Phoenix run."""
        if not session_id or not transcript:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._run_job(session_id, transcript, prosody_present),
                name=f"phoenix-bg-{session_id}",
            )
        except RuntimeError:
            loop = self._ensure_loop()
            asyncio.run_coroutine_threadsafe(
                self._run_job(session_id, transcript, prosody_present), loop
            )

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop and self._loop.is_running():
                return self._loop
            loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=self._loop_entry,
                args=(loop,),
                name="phoenix-bg-loop",
                daemon=True,
            )
            thread.start()
            self._loop = loop
            self._thread = thread
            return loop

    @staticmethod
    def _loop_entry(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    async def _run_job(
        self, session_id: str, transcript: str, prosody_present: bool
    ) -> None:
        start = time.perf_counter()
        previous = None
        try:
            previous = memory_manager.get_affect_snapshot(session_id)
        except Exception as exc:
            logger.warning("Affect snapshot lookup failed: %s", exc)

        try:
            classify_task = asyncio.to_thread(_phoenix_deep_text_classify, transcript)
            result = await asyncio.wait_for(classify_task, timeout=self.timeout_seconds)
            if not result:
                raise RuntimeError("Phoenix deep classify returned empty result")

            payload = self._compose_payload(result, previous, prosody_present)
            memory_manager.set_affect_snapshot(session_id, payload)
            latency_ms = (time.perf_counter() - start) * 1000.0
            self._record_success(latency_ms)
            success_rate = self._success_rate()
            logger.info(
                "Phoenix BG snapshot stored for %s: %s (conf=%.2f trend=%s, latency=%.0fms, p95=%.0fms, success_rate=%.1f%%)",
                session_id,
                payload["emotion"],
                payload["confidence"],
                payload["trend"],
                latency_ms,
                self.metrics.phoenix_bg_p95_latency_ms,
                success_rate * 100.0,
            )
            self._log_metrics("success", latency_ms)
        except asyncio.TimeoutError:
            latency_ms = (time.perf_counter() - start) * 1000.0
            self._record_failure(latency_ms)
            logger.warning(
                "Phoenix background timed out after %.0fms for session %s",
                latency_ms,
                session_id,
            )
            self._log_metrics("timeout", latency_ms)
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000.0
            self._record_failure(latency_ms)
            logger.warning(
                "Phoenix background failed for session %s: %s",
                session_id,
                exc,
            )
            self._log_metrics("error", latency_ms)

    def _compose_payload(
        self,
        result: Dict[str, Any],
        previous: Optional[Dict[str, Any]],
        prosody_present: bool,
    ) -> Dict[str, Any]:
        prev_conf = None
        if previous:
            try:
                prev_conf = float(previous.get("confidence"))
            except (TypeError, ValueError):
                prev_conf = None

        confidence = float(result.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        trend = "steady"
        if prev_conf is not None:
            delta = confidence - prev_conf
            if delta > 0.1:
                trend = "rising"
            elif delta < -0.1:
                trend = "falling"
        sentiment = _map_raw_label(result.get("label"))

        return {
            "emotion": result.get("label", "neutral"),
            "confidence": confidence,
            "trend": trend,
            "sentiment": sentiment,
            "voice_signal_present": bool(prosody_present),
            "updated_at": datetime.utcnow().isoformat(),
        }

    def _record_success(self, latency_ms: float) -> None:
        with self._lock:
            self.metrics.phoenix_bg_success_total += 1
            self._record_latency(latency_ms)

    def _record_failure(self, latency_ms: float) -> None:
        with self._lock:
            self.metrics.phoenix_bg_failure_total += 1
            self._record_latency(latency_ms)

    def _record_latency(self, latency_ms: float) -> None:
        self._latencies.append(latency_ms)
        if len(self._latencies) > 50:
            self._latencies.pop(0)
        ordered = sorted(self._latencies)
        if ordered:
            index = max(0, int(round(0.95 * len(ordered))) - 1)
            self.metrics.phoenix_bg_p95_latency_ms = ordered[index]

    def _success_rate(self) -> float:
        total = (
            self.metrics.phoenix_bg_success_total
            + self.metrics.phoenix_bg_failure_total
        )
        if total == 0:
            return 1.0
        return self.metrics.phoenix_bg_success_total / total

    def _log_metrics(self, status: str, latency_ms: float) -> None:
        logger.info(
            "Phoenix BG metrics | status=%s | latency_ms=%.0f | phoenix_bg_success_total=%d | phoenix_bg_failure_total=%d | phoenix_bg_p95_latency_ms=%.0f | phoenix_bg_success_rate=%.1f%%",
            status,
            latency_ms,
            self.metrics.phoenix_bg_success_total,
            self.metrics.phoenix_bg_failure_total,
            self.metrics.phoenix_bg_p95_latency_ms,
            self._success_rate() * 100.0,
        )


_phoenix_bg_executor = _PhoenixBackgroundExecutor()


def _map_raw_label(label: Optional[str]) -> str:
    normalized = (label or "").strip().lower()
    mapping = {
        "negative": "negative",
        "sad": "negative",
        "anger": "negative",
        "angry": "negative",
        "fear": "negative",
        "fearful": "negative",
        "grief": "negative",
        "panic": "negative",
        "depressed": "negative",
        "unhappy": "negative",
        "positive": "positive",
        "joy": "positive",
        "happy": "positive",
        "excited": "positive",
        "neutral": "neutral",
        "calm": "neutral",
    }
    return mapping.get(normalized, "neutral")


def _classify_with_phoenix(text: str) -> Optional[Emotion]:
    try:
        # Lazy import to avoid hard dep if not installed in some envs
        from phoenix.evals import llm_classify

        try:
            from phoenix.evals import GoogleGenAIModel
        except Exception as e:
            logger.info(
                f"Phoenix GoogleGenAIModel unavailable; skipping phoenix text classify: {e}"
            )
            return None
        model = GoogleGenAIModel(model="gemini-2.5-flash")
        get_settings()

        result = llm_classify(
            llm=model,
            data=[{"input": text}],
            template=(
                "Classify the overall sentiment of the INPUT as one of: positive, neutral, negative. "
                "Return only the label."
            ),
            label_schema={"positive", "neutral", "negative"},
        )
        # Phoenix may return a dict-like with labeled outputs; adapt safely
        label = None
        score = 0.0
        try:
            label = result["label"][0]
            score = float(result.get("score", [0.0])[0])
        except Exception:
            # Fallback parse
            label = "neutral"
            score = 0.5
        mapped = _map_raw_label(label)
        return Emotion(label=mapped, confidence=score)
    except Exception as e:
        logger.warning(f"Phoenix emotion model failed: {e}")
        return None


def _classify_with_llm(text: str) -> Emotion:
    try:
        from mistralai import Mistral
        import json

        settings = get_settings()
        if not settings.MISTRAL_API_KEY:
            return Emotion(label="neutral", confidence=0.5)
        client = Mistral(api_key=settings.MISTRAL_API_KEY)
        r = client.responses.create(
            model="mistral-small-latest",
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Classify sentiment of the following text as one of: positive, neutral, negative. "
                                'Respond with JSON: {"label": "...", "confidence": 0.0-1.0}. Text: '
                                f"{text}"
                            ),
                        }
                    ],
                }
            ],
        )
        content = getattr(r, "output_text", None)
        if not isinstance(content, str) or not content.strip():
            return Emotion(label="neutral", confidence=0.5)
        try:
            obj = json.loads(content)
            label = obj.get("label", "neutral")
            conf = float(obj.get("confidence", 0.5))
        except Exception:
            label = "neutral"
            conf = 0.5
        mapped = _map_raw_label(label)
        conf = max(0.0, min(1.0, conf))
        return Emotion(label=mapped, confidence=conf)
    except Exception:
        return Emotion(label="neutral", confidence=0.5)


def analyze_emotion_text(text: str) -> Emotion:
    # Define allowed emotion labels for database compatibility
    phoenix = _classify_with_phoenix(text)
    if phoenix:
        phoenix.label = _map_raw_label(phoenix.label)
        return phoenix

    result = _classify_with_llm(text)
    result.label = _map_raw_label(result.label)
    return result


def _keyword_emotion_lookup(text: str) -> Optional[Emotion]:
    """Lightweight heuristic matcher for richer emotion labels."""
    normalized = (text or "").lower()
    if not normalized.strip():
        return None

    keyword_map = {
        "sad": [
            "sad",
            "depressed",
            "down",
            "unhappy",
            "lonely",
            "miserable",
            "heartbroken",
            "blue",
            "груст",
            "печал",
            "одинок",
        ],
        "anxious": [
            "worried",
            "anxious",
            "stressed",
            "nervous",
            "overwhelmed",
            "concerned",
            "тревож",
            "волн",
            "беспок",
        ],
        "angry": [
            "angry",
            "mad",
            "furious",
            "annoyed",
            "frustrated",
            "irritated",
            "злой",
            "раздраж",
            "бесит",
        ],
        "fearful": [
            "afraid",
            "scared",
            "terrified",
            "frightened",
            "fearful",
            "страшн",
            "боюсь",
        ],
        "joy": [
            "happy",
            "joyful",
            "glad",
            "delighted",
            "счастл",
            "радост",
        ],
        "excited": [
            "excited",
            "thrilled",
            "pumped",
            "energized",
            "воодушевл",
            "энтузиазм",
        ],
        "grief": [
            "grief",
            "mourning",
            "bereaved",
            "скорб",
        ],
        "panic": [
            "panic",
            "panicking",
            "can't breathe",
            "losing control",
        ],
    }

    for label, keywords in keyword_map.items():
        if any(keyword in normalized for keyword in keywords):
            confidence = 0.85 if label in {"panic", "joy"} else 0.8
            return Emotion(label=label, confidence=confidence)
    return None


def _fallback_deep_classify(text: str) -> Dict[str, Any]:
    heuristic = _keyword_emotion_lookup(text)
    if heuristic:
        return {"label": heuristic.label, "confidence": heuristic.confidence}
    return {"label": "neutral", "confidence": 0.6}


def _phoenix_deep_text_classify(text: str) -> Optional[Dict[str, Any]]:
    """Run Phoenix deep classification for DIRECT/LIGHT background flows."""
    normalized = (text or "").strip()
    if not normalized:
        return None

    try:
        from phoenix.evals import llm_classify
        from phoenix.evals import GoogleGenAIModel
    except Exception as exc:
        logger.info("Phoenix deep text classify unavailable: %s", exc)
        return _fallback_deep_classify(normalized)

    try:
        model = GoogleGenAIModel(model="gemini-2.5-flash")
        template = (
            "Classify the user's primary emotional state from the INPUT. "
            f"Choose exactly one label from: {', '.join(_DEEP_EMOTION_RAILS)}. "
            "Return only the label."
        )
        result = llm_classify(
            llm=model,
            data=[{"input": normalized}],
            template=template,
            label_schema=set(_DEEP_EMOTION_RAILS),
        )
        label = str(result.get("label", ["neutral"])[0]).strip().lower()
        if label not in _DEEP_EMOTION_RAILS:
            label = "neutral"
        score_raw = result.get("score", [0.7])[0]
        confidence = max(0.0, min(1.0, float(score_raw)))
        return {"label": label, "confidence": confidence}
    except Exception as exc:
        logger.warning("Phoenix deep text classify failed: %s", exc)
        return _fallback_deep_classify(normalized)


def infer_text_emotion(text: str) -> Emotion:
    """Return best-effort emotion for text input with heuristics."""
    normalized = (text or "").strip()
    if not normalized:
        return Emotion(label="neutral", confidence=0.7)

    try:
        primary = analyze_emotion_text(normalized)
    except Exception as exc:
        logger.warning("Text emotion analysis failed: %s", exc)
        primary = Emotion(label="neutral", confidence=0.6)

    if primary and primary.label != "neutral":
        return primary

    heuristic = _keyword_emotion_lookup(normalized)
    if heuristic:
        return heuristic

    return primary if primary else Emotion(label="neutral", confidence=0.7)


def analyze_emotion_audio(wav_bytes: bytes) -> Emotion:
    """Classify emotion from audio using Phoenix Evals + Google Gemini.
    Requires GOOGLE_API_KEY in environment. Returns an Emotion model.

    Note: The database has a check constraint requiring emotion labels to be
    one of: positive, neutral, negative
    """
    # Quick guard: if audio is mock or too small, return neutral to avoid Phoenix errors
    try:
        if not wav_bytes or len(wav_bytes) < 2048 or wav_bytes.startswith(b"ID3mock"):
            return Emotion(label="neutral", confidence=0.5)
    except Exception:
        return Emotion(label="neutral", confidence=0.5)

    try:
        import base64
        import pandas as pd
        from phoenix.evals import llm_classify

        try:
            from phoenix.evals import GoogleGenAIModel
            from phoenix.evals.templates import (
                ClassificationTemplate,
                PromptPartContentType,
                PromptPartTemplate,
            )
        except Exception as e:
            logger.info(
                "Phoenix GoogleGenAIModel unavailable; returning neutral for audio classify: %s",
                e,
            )
            return Emotion(label="neutral", confidence=0.5)

        settings = get_settings()
        if not getattr(settings, "GOOGLE_API_KEY", None):
            logger.warning(
                "GOOGLE_API_KEY not set - skipping Phoenix audio emotion classification"
            )
            return Emotion(label="neutral", confidence=0.5)

        # Define emotion rails (categories)
        EMOTION_RAILS = [
            "anger",
            "happiness",
            "excitement",
            "sadness",
            "neutral",
            "frustration",
            "fear",
            "surprise",
            "disgust",
            "other",
        ]

        # Create improved emotion template
        emotion_template = ClassificationTemplate(
            rails=EMOTION_RAILS,
            template=[
                PromptPartTemplate(
                    content_type=PromptPartContentType.TEXT,
                    template=(
                        "You are an AI system designed to classify emotions in audio files.\n"
                        "Analyze the provided audio and classify the primary emotion based on tone, pitch, pace, volume, and intensity.\n"
                        f"Valid emotions: {EMOTION_RAILS}\n"
                        "Return ONLY one word from the list."
                    ),
                ),
                PromptPartTemplate(
                    content_type=PromptPartContentType.AUDIO,
                    template="{audio}",
                ),
                PromptPartTemplate(
                    content_type=PromptPartContentType.TEXT,
                    template="Your response must be exactly one word from the valid emotions list.",
                ),
            ],
        )

        # 1) encode audio to base64
        audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")

        # 2) dataframe with expected column name 'audio'
        df = pd.DataFrame([{"audio": audio_b64}])

        # 3) model: gemini
        model = GoogleGenAIModel(model="gemini-2.5-flash")

        # 4) run classification with improved template
        results = llm_classify(
            data=df,
            model=model,
            template=emotion_template,
            rails=EMOTION_RAILS,
            provide_explanation=False,
            run_sync=True,
            verbose=False,
        )

        # 5) extract single label
        label = str(results["label"].iloc[0]).strip().lower()
        valid = [r.lower() for r in EMOTION_RAILS]
        if label not in valid:
            label = "neutral"

        # Map emotion labels to database-allowed values (positive, neutral, negative)
        # This is required by the database check constraint
        emotion_mapping = {
            "happiness": "positive",
            "excitement": "positive",
            "surprise": "positive",
            "neutral": "neutral",
            "anger": "negative",
            "sadness": "negative",
            "frustration": "negative",
            "fear": "negative",
            "disgust": "negative",
            "other": "neutral",
        }

        # Map to allowed database values
        db_label = emotion_mapping.get(label, "neutral")

        # Confidence not provided by default template; set midpoint
<<<<<<< HEAD
        return Emotion(
            label=db_label, confidence=0.8
        )  # Higher confidence with improved template
    except RuntimeError as e:
        # Specifically catch event loop errors
        if "event loop" in str(e).lower() or "asyncio" in str(e).lower():
            logger.warning(
                f"Audio emotion classification failed due to event loop conflict: {e}. Returning neutral."
            )
        else:
            logger.warning(
                f"Audio emotion classification failed with RuntimeError: {e}"
            )
=======
        return Emotion(label=db_label, confidence=0.8)  # Higher confidence with improved template
    except RuntimeError as e:
        # Specifically catch event loop errors
        if "event loop" in str(e).lower() or "asyncio" in str(e).lower():
            logger.warning(f"Audio emotion classification failed due to event loop conflict: {e}. Returning neutral.")
        else:
            logger.warning(f"Audio emotion classification failed with RuntimeError: {e}")
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        return Emotion(label="neutral", confidence=0.5)
    except Exception as e:
        logger.warning(f"Audio emotion classification failed: {e}")
        return Emotion(label="neutral", confidence=0.5)


def trigger_phoenix_bg(session_id: str, transcript: str, prosody_present: bool) -> None:
    """Schedule Phoenix deep classification without blocking response latency."""
    text = (transcript or "").strip()
    if not session_id or not text:
        return
    try:
        _phoenix_bg_executor.submit(session_id, text, prosody_present)
    except Exception as exc:
        logger.warning("Failed to trigger Phoenix background task: %s", exc)
