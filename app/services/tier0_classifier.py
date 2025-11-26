"""Tier-0 Fast Classifier with Mistral Small and Rule-Based Fallback.

Provides ultra-fast intent and emotion classification with <700ms P95 latency.
Falls back to rule-based patterns if LLM fails or times out.
"""

import asyncio
<<<<<<< HEAD
=======
import json
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
import logging
import re
import time
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
<<<<<<< HEAD
=======
from threading import Lock

from prometheus_client import Counter, Gauge  # type: ignore[import]
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)

try:
    from mistralai import Mistral
except ImportError:  # pragma: no cover - optional dependency for fast path
    Mistral = None
from app.config import get_settings

logger = logging.getLogger("sophia-backend")

# Intent types
INTENT_GREETING = "greeting"
INTENT_CASUAL = "casual"
INTENT_EMOTIONAL = "emotional_sharing"
INTENT_CRISIS = "crisis"
INTENT_KNOWLEDGE = "knowledge"

# Emotions
EMOTION_NEUTRAL = "neutral"
EMOTION_JOY = "joy"
EMOTION_SAD = "sad"
EMOTION_ANXIOUS = "anxious"
EMOTION_ANGRY = "angry"
EMOTION_FEARFUL = "fearful"
EMOTION_GRIEF = "grief"
EMOTION_PANIC = "panic"
EMOTION_EXCITED = "excited"

# Crisis keywords (self-harm, suicide)
CRISIS_PATTERNS = [
    r"\b(kill|suicide|die|death|end.*life|hurt.*myself|harm.*myself)\b",
    r"\b(don'?t\s+want\s+to\s+live|want\s+to\s+die|life.*not.*worth)\b",
    r"\b(не.*хоч.*жить|суицид|убить.*себ|покончить|умер)",
    r"\b(cut.*myself|overdose|jump.*off|hang.*myself)\b",
    r"\b(better.*if.*died|end.*it.*all|take.*my.*life)\b",
]

<<<<<<< HEAD
=======
TIER0_SYSTEM_PROMPT = (
    "You label short voice transcripts for Sophia. "
    "Allowed intents: greeting, casual, emotional_sharing, crisis, knowledge. "
    "Allowed emotions: neutral, joy, sad, anxious, angry, fearful, grief, panic, excited. "
    "Return JSON with keys intent, emotion, confidence (0-1). "
    "If unsure, prefer casual + neutral."
)

TIER0_FEW_SHOT_EXAMPLES = [
    (
        "hey sophia, good morning!",
        {"intent": INTENT_GREETING, "emotion": EMOTION_JOY, "confidence": 0.85},
    ),
    (
        "i feel so anxious about my interview tomorrow",
        {"intent": INTENT_EMOTIONAL, "emotion": EMOTION_ANXIOUS, "confidence": 0.82},
    ),
    (
        "how does staking on ethereum work?",
        {"intent": INTENT_KNOWLEDGE, "emotion": EMOTION_NEUTRAL, "confidence": 0.74},
    ),
]

LLM_RESPONSE_SCHEMA = {
    "name": "Tier0Classification",
    "schema": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": [
                    INTENT_GREETING,
                    INTENT_CASUAL,
                    INTENT_EMOTIONAL,
                    INTENT_CRISIS,
                    INTENT_KNOWLEDGE,
                ],
            },
            "emotion": {
                "type": "string",
                "enum": [
                    EMOTION_NEUTRAL,
                    EMOTION_JOY,
                    EMOTION_SAD,
                    EMOTION_ANXIOUS,
                    EMOTION_ANGRY,
                    EMOTION_FEARFUL,
                    EMOTION_GRIEF,
                    EMOTION_PANIC,
                    EMOTION_EXCITED,
                ],
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
        },
        "required": ["intent", "emotion", "confidence"],
        "additionalProperties": False,
    },
}

tier0_timeout_count = Counter(
    "tier0_timeout_count", "Number of tier-0 LLM timeout events"
)
tier0_json_error_count = Counter(
    "tier0_json_error_count", "Number of tier-0 LLM JSON parsing failures"
)
tier0_success_rate_percent = Gauge(
    "tier0_success_rate_percent",
    "Tier-0 LLM success rate (percentage of calls that avoided fallback)",
)
tier0_latency_ms = Gauge(
    "tier0_latency_ms",
    "Latest tier-0 classification latency in milliseconds",
)
tier0_latency_avg_ms = Gauge(
    "tier0_latency_avg_ms",
    "Running average of tier-0 classification latency in milliseconds",
)

_tier0_success_lock = Lock()
_tier0_success_total = 0
_tier0_total_requests = 0
_tier0_latency_total_ms = 0.0

_INTENT_TEXT_PATTERN = re.compile(r"intent\s*(?:is|:)\s*([a-z_]+)", re.IGNORECASE)
_EMOTION_TEXT_PATTERN = re.compile(r"emotion\s*(?:is|:)\s*([a-z_]+)", re.IGNORECASE)
_CONFIDENCE_TEXT_PATTERN = re.compile(
    r"confidence\s*(?:is|:)\s*([0-9]+(?:\.[0-9]+)?%?)", re.IGNORECASE
)

>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)

@dataclass
class ClassificationResult:
    """Result of tier-0 classification"""

    type: str  # intent type
    emotion: str  # emotion label
    confidence: float  # classification confidence (0-1)
    asr_confidence: float  # ASR confidence (from prosody if available)
    voice_signal_present: bool  # whether voice signal was detected
    latency_ms: float  # classification latency
    fallback_used: bool  # whether rule-based fallback was used
    source: str  # classification source: "mistral_llm" or "rule_based_fallback"


<<<<<<< HEAD
=======
class LLMParsingError(ValueError):
    """Raised when LLM response cannot be parsed into structured output."""

    def __init__(self, message: str, raw_content: str):
        super().__init__(message)
        self.raw_content = raw_content


def _truncate_for_log(text: str, limit: int = 240) -> str:
    if text is None:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…"


def _record_metrics(
    llm_succeeded: bool, alert_threshold: float, latency_ms: float
) -> None:
    success_rate = 0.0
    avg_latency = 0.0
    global _tier0_success_total, _tier0_total_requests, _tier0_latency_total_ms
    with _tier0_success_lock:
        _tier0_total_requests += 1
        if llm_succeeded:
            _tier0_success_total += 1
        _tier0_latency_total_ms += latency_ms
        success_rate = (
            (_tier0_success_total / _tier0_total_requests) * 100
            if _tier0_total_requests
            else 0.0
        )
        avg_latency = (
            _tier0_latency_total_ms / _tier0_total_requests
            if _tier0_total_requests
            else 0.0
        )
        tier0_success_rate_percent.set(success_rate)
        tier0_latency_ms.set(latency_ms)
        tier0_latency_avg_ms.set(avg_latency)
    threshold_percent = alert_threshold * 100
    if success_rate < threshold_percent:
        logger.error(
            "Tier-0 success rate alert: %.1f%% fell below %.0f%% threshold",
            success_rate,
            threshold_percent,
        )


def _strip_code_fences(payload: str) -> str:
    """Remove common Markdown fences from LLM responses."""
    text = payload.strip()
    if text.startswith("```"):
        text = text[3:]
        if text.lower().startswith("json"):
            text = text[4:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return text


def _coerce_llm_payload(payload: Any) -> Tuple[str, str, float]:
    """Extract intent/emotion/confidence from a parsed JSON payload."""
    if not isinstance(payload, dict):
        raise ValueError("LLM payload is not a JSON object")
    intent_raw = payload.get("intent")
    emotion_raw = payload.get("emotion")
    confidence_raw = payload.get("confidence", 0.6)

    intent = str(intent_raw).strip().lower() if intent_raw else INTENT_CASUAL
    emotion = str(emotion_raw).strip().lower() if emotion_raw else EMOTION_NEUTRAL
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.6
    confidence = max(0.0, min(1.0, confidence))
    return intent, emotion, confidence


def _parse_textual_llm_response(text: str) -> Tuple[str, str, float]:
    """Fallback parser for plain-text LLM outputs."""
    intent_match = _INTENT_TEXT_PATTERN.search(text)
    emotion_match = _EMOTION_TEXT_PATTERN.search(text)
    if not (intent_match and emotion_match):
        raise LLMParsingError("LLM response missing intent/emotion hints", text)

    confidence_match = _CONFIDENCE_TEXT_PATTERN.search(text)
    if confidence_match:
        confidence_str = confidence_match.group(1).replace("%", "")
        try:
            confidence = float(confidence_str)
            if confidence > 1:  # convert percentages such as 85
                confidence /= 100
        except ValueError:
            confidence = 0.6
    else:
        confidence = 0.6
    confidence = max(0.0, min(1.0, confidence))

    logger.warning(
        "Tier-0: Falling back to heuristic parse for payload: %s",
        _truncate_for_log(text),
    )
    return (
        intent_match.group(1).strip().lower(),
        emotion_match.group(1).strip().lower(),
        confidence,
    )


def _parse_llm_response(raw_content: str) -> Tuple[str, str, float]:
    """Parse Mistral response into structured data with fallbacks."""
    if not raw_content or not raw_content.strip():
        raise ValueError("Empty response from Mistral API")

    cleaned = _strip_code_fences(raw_content)

    # Attempt direct JSON parsing (handles code fences and added explanations)
    json_candidates = []
    if cleaned.startswith("{"):
        json_candidates.append(cleaned)
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_candidates.append(cleaned[first_brace : last_brace + 1])

    json_error_recorded = False
    for candidate in json_candidates:
        try:
            payload = json.loads(candidate)
            return _coerce_llm_payload(payload)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            if not json_error_recorded:
                tier0_json_error_count.inc()
                json_error_recorded = True
            logger.warning(
                "Tier-0: Failed to parse JSON candidate (%s): %s",
                _truncate_for_log(candidate),
                exc,
            )
            continue

    # Plain-text fallback ("The intent is ...")
    try:
        if json_candidates and not json_error_recorded:
            tier0_json_error_count.inc()
            json_error_recorded = True
        return _parse_textual_llm_response(cleaned)
    except LLMParsingError as exc:
        if not json_error_recorded:
            tier0_json_error_count.inc()
        logger.error(
            "Tier-0: Unable to parse LLM payload after fallbacks: %s",
            _truncate_for_log(cleaned),
        )
        raise


>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
def _get_mistral_client() -> Mistral:
    """Get Mistral API client"""
    if Mistral is None:
        raise RuntimeError("mistralai SDK is not installed")
    settings = get_settings()
    if not settings.MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY is not set")
    return Mistral(api_key=settings.MISTRAL_API_KEY)


def _detect_crisis(text: str) -> bool:
    """Detect crisis/self-harm phrases in text (rule-based, always fast)"""
    text_lower = text.lower()
    for pattern in CRISIS_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            logger.warning(f"🚨 CRISIS DETECTED in text: '{text[:50]}...'")
            return True
    return False


def _rule_based_classify(
    transcript: str, prosody: Optional[Dict[str, Any]] = None
) -> Tuple[str, str, float]:
    """Rule-based intent and emotion classification (< 1ms fallback).

    Returns: (intent, emotion, confidence)
    """
    text_lower = transcript.lower().strip()

    # 1. Crisis detection (highest priority)
    if _detect_crisis(transcript):
        emotion = (
            EMOTION_PANIC
            if prosody and prosody.get("intensity", 0) > 0.7
            else EMOTION_ANXIOUS
        )
        return INTENT_CRISIS, emotion, 0.95

    # 2. Detect emotions first (before intent detection)
    emotion_keywords = {
        EMOTION_SAD: [
            "sad",
            "depressed",
            "down",
            "upset",
            "unhappy",
            "lonely",
            "miserable",
            "blue",
            "heartbroken",
            "feeling sad",
            "feel sad",
            "i'm sad",
            "грустн",
            "печал",
            "тоск",
            "одинок",
        ],
        EMOTION_ANXIOUS: [
            "worried",
            "anxious",
            "stressed",
            "nervous",
            "concerned",
            "uneasy",
            "tense",
            "overwhelmed",
            "feeling anxious",
            "feel worried",
            "i'm worried",
            "тревож",
            "беспоко",
            "волну",
        ],
        EMOTION_ANGRY: [
            "angry",
            "mad",
            "furious",
            "annoyed",
            "frustrated",
            "irritated",
            "pissed",
            "enraged",
            "feeling angry",
            "feel angry",
            "i'm angry",
            "злой",
            "раздраж",
            "бесит",
        ],
        EMOTION_FEARFUL: [
            "scared",
            "afraid",
            "terrified",
            "frightened",
            "fearful",
            "panicked",
            "feeling scared",
            "feel afraid",
            "i'm scared",
            "страшн",
            "боюсь",
        ],
        EMOTION_JOY: [
            "happy",
            "joyful",
            "glad",
            "cheerful",
            "delighted",
            "pleased",
            "excited",
            "thrilled",
            "feeling happy",
            "feel happy",
            "i'm happy",
            "радост",
            "счастлив",
            "весел",
        ],
        EMOTION_EXCITED: [
            "excited",
            "thrilled",
            "pumped",
            "energized",
            "enthusiastic",
            "eager",
            "feeling excited",
            "feel excited",
            "i'm excited",
            "взволнован",
            "воодушевл",
        ],
    }

    detected_emotion = EMOTION_NEUTRAL
    max_emotion_score = 0

    for emotion, keywords in emotion_keywords.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > max_emotion_score:
            max_emotion_score = score
            detected_emotion = emotion

    # Adjust emotion based on prosody intensity
    if max_emotion_score > 0 and prosody and prosody.get("intensity", 0) > 0.8:
        if detected_emotion == EMOTION_ANXIOUS:
            detected_emotion = EMOTION_PANIC

    # 3. Intent detection (using detected emotion)
    # 3a. Greeting detection (English + Russian variants)
    greeting_patterns = [
        r"\b(hi|hello|hey|yo|sup|greetings)\b",
        r"\b(good\s+(?:morning|afternoon|evening|day))\b",
        r"\b(привет|здраст[вуйте]*|здравств[уйте]*)\b",
        r"\b(доброе?\s+утро|добры[йе]\s+день|добры[йе]\s+вечер|доброй\s+ночи)\b",
    ]
    greeting_terms = [
        "доброе утро",
        "добрый день",
        "добрый вечер",
        "доброй ночи",
    ]
    is_greeting = any(
        re.search(pattern, text_lower) for pattern in greeting_patterns
    ) or any(term in text_lower for term in greeting_terms)

    # 3b. Check if there are emotional keywords
    has_emotion = max_emotion_score > 0

    if is_greeting:
        # If greeting with emotion, use detected emotion; otherwise use joy as default
        emotion = detected_emotion if has_emotion else EMOTION_JOY
        confidence = 0.80 if has_emotion else 0.85
        return INTENT_GREETING, emotion, confidence

    # 3c. Emotional sharing (when emotions detected without greeting)
    if has_emotion:
        return INTENT_EMOTIONAL, detected_emotion, 0.75

    # 4. Knowledge/DeFi question detection
    knowledge_keywords = [
        "what",
        "how",
        "why",
        "explain",
        "tell",
        "defi",
        "yield",
        "staking",
        "стейкинг",
        "token",
        "tokenomics",
        "blockchain",
        "блокчейн",
        "ethereum",
        "liquidity",
        "liquidity pool",
        "smart contract",
        "смарт контракт",
        "crypto",
        "крипт",
        "что",
        "как",
        "почему",
        "объясни",
        "расскажи",
    ]
    if any(kw in text_lower for kw in knowledge_keywords):
        return INTENT_KNOWLEDGE, EMOTION_NEUTRAL, 0.70

    # 5. Default: casual conversation
    return INTENT_CASUAL, EMOTION_NEUTRAL, 0.60


<<<<<<< HEAD
=======
def _build_llm_prompt(transcript: str) -> str:
    """Create a compact prompt with few-shot examples."""
    sanitized = transcript.strip()
    text_fragment = json.dumps(sanitized, ensure_ascii=False)
    examples = "; ".join(
        f'{json.dumps(text, ensure_ascii=False)} -> '
        f'{json.dumps(example, ensure_ascii=False)}'
        for text, example in TIER0_FEW_SHOT_EXAMPLES
    )
    return (
        f"Text: {text_fragment}\n"
        f"Examples: {examples}\n"
        "Return JSON with intent, emotion, confidence."
    )


>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
async def _llm_classify(
    transcript: str, timeout_ms: int = 500
) -> Tuple[str, str, float]:
    """LLM-based classification using Mistral Small with timeout.

    Returns: (intent, emotion, confidence)
    Raises: asyncio.TimeoutError if exceeds timeout
    """

<<<<<<< HEAD
    prompt = f"""Classify the following user message into intent and emotion.

Intent types:
- greeting: user is saying hello/hi
- casual: casual conversation, chitchat
- emotional_sharing: user sharing feelings/emotions
- crisis: mentions of self-harm, suicide, or severe distress
- knowledge: asking for information/explanation

Emotions: neutral, joy, sad, anxious, angry, fearful, grief, panic, excited

User message: "{transcript}"

Respond ONLY in this JSON format:
{{"intent": "...", "emotion": "...", "confidence": 0.0-1.0}}"""
=======
    prompt = _build_llm_prompt(transcript)
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)

    client = _get_mistral_client()

    def _invoke() -> Tuple[str, str, float]:
<<<<<<< HEAD
        response = client.chat.complete(
            model="mistral-small-latest",  # Fast model
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=50,
        )
        content = response.choices[0].message.content

        # Debug logging
        logger.debug(f"Mistral API response content: {content}")

        # Parse JSON response
        import json

        if not content or not content.strip():
            raise ValueError("Empty response from Mistral API")
        result = json.loads(content.strip())
        return result["intent"], result["emotion"], result["confidence"]
=======
        responses_iface = getattr(client, "responses", None)
        request_messages = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": TIER0_SYSTEM_PROMPT,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    }
                ],
            },
        ]

        if responses_iface is not None:
            try:
                response = responses_iface.create(
                    model="mistral-small-latest",
                    input=request_messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": LLM_RESPONSE_SCHEMA,
                    },
                    temperature=0.0,
                    max_output_tokens=64,
                )
                content = getattr(response, "output_text", None)
                if isinstance(content, str) and content.strip():
                    logger.debug(
                        "Tier-0: Responses API content: %s",
                        _truncate_for_log(content),
                    )
                    return _parse_llm_response(content)
                logger.debug(
                    "Tier-0: Responses API returned empty output_text, fallback to chat"
                )
            except Exception as responses_exc:
                logger.debug(
                    "Tier-0: Responses API unavailable (%s), fallback to chat",
                    responses_exc,
                )

        chat_response = client.chat.complete(
            model="mistral-small-latest",
            messages=[
                {"role": "system", "content": TIER0_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=64,
        )
        content = chat_response.choices[0].message.content
        logger.debug("Tier-0: Chat API content: %s", _truncate_for_log(content or ""))

        return _parse_llm_response(content or "")
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)

    return await asyncio.to_thread(_invoke)


async def classify_tier0_fast(
<<<<<<< HEAD
    transcript: str, prosody: Optional[Dict[str, Any]] = None, timeout_ms: int = 500
=======
    transcript: str,
    prosody: Optional[Dict[str, Any]] = None,
    timeout_ms: Optional[int] = None,
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
) -> ClassificationResult:
    """Ultra-fast tier-0 classification with Mistral Small + rule-based fallback.

    Args:
        transcript: User speech transcript
        prosody: Optional prosody features dict with keys:
                 - intensity: 0-1 (voice intensity)
                 - pitch: Hz (voice pitch)
                 - confidence: 0-1 (ASR confidence)
<<<<<<< HEAD
        timeout_ms: Timeout for LLM classification (default 500ms)
=======
        timeout_ms: Optional timeout override in ms.
                    None → settings.TIER0_LLM_TIMEOUT_MS (default 1000ms)
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)

    Returns:
        ClassificationResult with intent, emotion, confidence, and metadata

    Guarantees:
        - P95 latency ≤ 700ms (including fallback)
        - Always returns a result (fallback handles all errors)
        - Crisis detection works in fallback mode
    """

<<<<<<< HEAD
=======
    settings = get_settings()
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    start_time = time.perf_counter()
    fallback_used = False

    # Extract prosody features
    asr_confidence = prosody.get("confidence", 1.0) if prosody else 1.0
    voice_signal_present = prosody.get("voice_detected", True) if prosody else True

<<<<<<< HEAD
    # Try LLM classification first
    try:
        logger.info(f"Tier-0: Attempting LLM classification (timeout={timeout_ms}ms)")
        intent, emotion, confidence = await asyncio.wait_for(
            _llm_classify(transcript, timeout_ms),
            timeout=timeout_ms / 1000.0,
        )

        # Adjust emotion based on prosody
        if prosody and prosody.get("intensity", 0) > 0.8:
            if emotion == EMOTION_ANXIOUS:
=======
    effective_timeout_ms = (
        timeout_ms if timeout_ms is not None else settings.TIER0_LLM_TIMEOUT_MS
    )
    timeout_grace_ms = max(0, settings.TIER0_LLM_TIMEOUT_GRACE_MS)
    wait_for_seconds = (effective_timeout_ms + timeout_grace_ms) / 1000.0
    max_attempts = max(1, settings.TIER0_LLM_MAX_RETRIES + 1)
    backoff_base_ms = max(0, settings.TIER0_LLM_BACKOFF_BASE_MS)
    backoff_factor = max(1.0, settings.TIER0_LLM_BACKOFF_FACTOR)

    classification: Optional[Tuple[str, str, float]] = None
    llm_success = False
    last_error: Optional[Exception] = None

    for attempt in range(max_attempts):
        attempt_num = attempt + 1
        try:
            logger.info(
                "Tier-0: LLM attempt %s/%s (timeout=%sms, grace=%sms)",
                attempt_num,
                max_attempts,
                effective_timeout_ms,
                timeout_grace_ms,
            )
            intent, emotion, confidence = await asyncio.wait_for(
                _llm_classify(transcript, effective_timeout_ms),
                timeout=wait_for_seconds,
            )

            if prosody and prosody.get("intensity", 0) > 0.8 and emotion == EMOTION_ANXIOUS:
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
                emotion = EMOTION_PANIC
                logger.info(
                    "Tier-0: Adjusted emotion anxious → panic (high prosody intensity)"
                )

<<<<<<< HEAD
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Tier-0 LLM classification completed: intent={intent}, emotion={emotion}, "
            f"confidence={confidence:.2f}, latency={latency_ms:.1f}ms"
        )

    except asyncio.TimeoutError:
        # Timeout - use rule-based fallback
        logger.warning(
            f"Tier-0: LLM timeout ({timeout_ms}ms), using rule-based fallback"
        )
        fallback_used = True
        intent, emotion, confidence = _rule_based_classify(transcript, prosody)
        latency_ms = (time.perf_counter() - start_time) * 1000

    except Exception as e:
        # Any error - use rule-based fallback
        logger.warning(f"Tier-0: LLM error ({e}), using rule-based fallback")
        fallback_used = True
        intent, emotion, confidence = _rule_based_classify(transcript, prosody)
        latency_ms = (time.perf_counter() - start_time) * 1000
=======
            classification = (intent, emotion, confidence)
            llm_success = True
            break
        except asyncio.TimeoutError as timeout_exc:
            tier0_timeout_count.inc()
            last_error = timeout_exc
            logger.warning(
                "Tier-0: LLM timeout on attempt %s/%s (timeout=%sms)",
                attempt_num,
                max_attempts,
                effective_timeout_ms,
            )
        except LLMParsingError as parse_exc:
            last_error = parse_exc
            logger.warning(
                "Tier-0: LLM parsing error on attempt %s/%s: %s | payload=%s",
                attempt_num,
                max_attempts,
                parse_exc,
                _truncate_for_log(parse_exc.raw_content),
            )
        except Exception as err:
            last_error = err
            logger.warning(
                "Tier-0: LLM error on attempt %s/%s: %s",
                attempt_num,
                max_attempts,
                err,
            )

        if attempt < max_attempts - 1:
            backoff_ms = backoff_base_ms * (backoff_factor**attempt)
            if backoff_ms > 0:
                await asyncio.sleep(backoff_ms / 1000.0)

    if not llm_success or classification is None:
        fallback_used = True
        if last_error:
            logger.warning(
                "Tier-0: Falling back to rule-based classifier after LLM failures (%s)",
                last_error,
            )
        classification = _rule_based_classify(transcript, prosody)

    intent, emotion, confidence = classification
    latency_ms = (time.perf_counter() - start_time) * 1000

    if llm_success:
        logger.info(
            "Tier-0 LLM classification completed: intent=%s, emotion=%s, "
            "confidence=%.2f, latency=%.1fms",
            intent,
            emotion,
            confidence,
            latency_ms,
        )
    else:
        logger.warning(
            "Tier-0 rule-based classification used (intent=%s, emotion=%s, latency=%.1fms)",
            intent,
            emotion,
            latency_ms,
        )
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)

    # Double-check for crisis in fallback mode (safety net)
    if fallback_used and _detect_crisis(transcript):
        intent = INTENT_CRISIS
        emotion = (
            EMOTION_PANIC
            if prosody and prosody.get("intensity", 0) > 0.7
            else EMOTION_ANXIOUS
        )
        confidence = 0.95
        logger.warning("Tier-0: Crisis detected in fallback mode")

<<<<<<< HEAD
=======
    _record_metrics(
        llm_success, settings.TIER0_SUCCESS_ALERT_THRESHOLD, latency_ms
    )

>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    return ClassificationResult(
        type=intent,
        emotion=emotion,
        confidence=confidence,
        asr_confidence=asr_confidence,
        voice_signal_present=voice_signal_present,
        latency_ms=latency_ms,
        fallback_used=fallback_used,
        source="rule_based_fallback" if fallback_used else "mistral_llm",
    )


# Synchronous wrapper for compatibility
def classify_tier0_fast_sync(
<<<<<<< HEAD
    transcript: str, prosody: Optional[Dict[str, Any]] = None, timeout_ms: int = 500
) -> Dict[str, Any]:
    """Synchronous wrapper for classify_tier0_fast().

=======
    transcript: str,
    prosody: Optional[Dict[str, Any]] = None,
    timeout_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Synchronous wrapper for classify_tier0_fast().

    Args:
        transcript: User speech transcript.
        prosody: Optional prosody feature dict.
        timeout_ms: Optional timeout override; None uses settings default.

>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    Returns dict with keys: type, emotion, confidence, asr_confidence,
                            voice_signal_present, latency_ms, fallback_used
    """
    coro = classify_tier0_fast(transcript, prosody, timeout_ms)
    try:
        result = asyncio.run(coro)
    except RuntimeError as err:
        if "asyncio.run()" not in str(err):
            raise
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(coro)
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    return {
        "type": result.type,
        "emotion": result.emotion,
        "confidence": result.confidence,
        "asr_confidence": result.asr_confidence,
        "voice_signal_present": result.voice_signal_present,
        "latency_ms": result.latency_ms,
        "fallback_used": result.fallback_used,
    }
