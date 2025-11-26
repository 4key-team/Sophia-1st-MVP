"""Mistral SDK integrations for transcription, text generation, and streaming replies."""

import base64
import logging
import mimetypes
from typing import Callable, List, Dict, Optional, Tuple
<<<<<<< HEAD
=======
from urllib.parse import urljoin
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)

from mistralai import Mistral

from app.config import get_settings

logger = logging.getLogger("sophia-backend")
_client_base_url_logged = False


def _audio_file_payload(wav_bytes: bytes) -> Dict[str, object]:
    """Return a dict compatible with the Voxtral SDK's file parameter."""

    default_mime = "audio/wav"

    # Ensure we always provide some bytes, even for empty clips.
    raw_bytes = wav_bytes or b""

    # Rough magic-byte sniffing for better filenames (SDK inspects extension).
    header = raw_bytes[:4]
    if header == b"RIFF":
        ext = ".wav"
    elif header[:3] == b"ID3" or (
<<<<<<< HEAD
        raw_bytes and raw_bytes[0] == 0xFF and (raw_bytes[1] & 0xE0) == 0xE0
=======
        raw_bytes
        and raw_bytes[0] == 0xFF
        and (raw_bytes[1] & 0xE0) == 0xE0
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    ):
        ext = ".mp3"
    elif header == b"OggS":
        ext = ".ogg"
    elif header == bytes([0x1A, 0x45, 0xDF, 0xA3]):
        ext = ".webm"
    else:
        ext = ".wav"

    filename = f"audio{ext}"
    mime = mimetypes.types_map.get(ext.lower(), default_mime)

    return {
        "file_name": filename,
        "content": raw_bytes,
        "content_type": mime,
    }


_RESPONSES_AVAILABLE = True


def _extract_http_details(exc: Exception) -> Tuple[Optional[int], Optional[str]]:
    """Best-effort extraction of status code and textual response from an exception."""

    status: Optional[int] = None
    text: Optional[str] = None

    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if value is not None:
            try:
                status = int(value)
                break
            except (TypeError, ValueError):
                pass

    response = getattr(exc, "response", None)
    if response is not None:
        for attr in ("status_code", "status"):
            value = getattr(response, attr, None)
            if value is not None:
                try:
                    status = int(value)
                    break
                except (TypeError, ValueError):
                    pass

        text_candidate = None
        for attr in ("text", "content", "body"):
            value = getattr(response, attr, None)
            if callable(value):
                try:
                    value = value()
                except Exception:
                    value = None
            if value is None:
                continue
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8", "ignore")
                except Exception:
                    value = None
            if isinstance(value, str) and value.strip():
                text_candidate = value.strip()
                break
        if text_candidate:
            text = text_candidate

    if text is None:
        for attr in ("message", "detail"):
            value = getattr(exc, attr, None)
            if isinstance(value, str) and value.strip():
                text = value.strip()
                break

    if text is not None and len(text) > 500:
        text = text[:497] + "..."

    return status, text

<<<<<<< HEAD

=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
CancelCallback = Callable[[], None]


def _noop_cancel() -> None:
    return None


def _ensure_cancel(cb: Optional[CancelCallback]) -> CancelCallback:
    return cb if cb is not None else _noop_cancel


def _client() -> Mistral:
    settings = get_settings()
    if not settings.MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY is not set")
    client = Mistral(
        api_key=settings.MISTRAL_API_KEY,
        server_url=settings.MISTRAL_API_BASE,
    )

    global _client_base_url_logged
    if not _client_base_url_logged:
        logger.info(
            "Configured Mistral client base URL: %s",
            settings.MISTRAL_API_BASE,
        )
        _client_base_url_logged = True

    return client


def transcribe_audio_with_voxtral(
    wav_bytes: bytes,
    cancel_check: Optional[CancelCallback] = None,
) -> str:
    """Transcribe audio using Mistral Voxtral if available; fallback to Gemini.
    Returns plain text transcript.
    """
    cancel = _ensure_cancel(cancel_check)
    cancel()
    settings = get_settings()

    # Preferred: Mistral transcription endpoint (voxtral-large-latest for best accuracy)
    try:
        client = _client()
        cancel()

        # Provide a filename; SDK inspects content
        # Detect common audio container by magic bytes to choose a helpful filename
        def _detect_ext(data: bytes) -> str:
            try:
                if not data or len(data) < 4:
                    return ".wav"
                b0 = data[:4]
                if b0 == b"RIFF":
                    return ".wav"
                if b0[:3] == b"ID3" or (data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
                    return ".mp3"
                if data[:4] == b"OggS":
                    return ".ogg"
                # WebM/Matroska EBML header
                if data[:4] == bytes([0x1A, 0x45, 0xDF, 0xA3]):
                    return ".webm"
                return ".wav"
            except Exception:
                return ".wav"

        file_name = f"audio{_detect_ext(wav_bytes)}"
        # Create a proper file-like object for Mistral SDK
        from mistralai.models import File

        file_obj = File(
            file_name=file_name,
            content=wav_bytes,
        )
        resp = client.audio.transcriptions.complete(
            model="voxtral-mini-latest",
            file=file_obj,
        )
        cancel()
        # Try robust extraction from SDK response
        # Known SDK returns may have attributes like 'text' or dict-like structures
        text = None
        for key in ("text", "output_text", "transcript"):
            try:
                val = getattr(resp, key, None)
                if isinstance(val, str) and val.strip():
                    text = val.strip()
                    break
            except Exception:
                pass
        if text is None:
            try:
                # If resp is dict-like
                text = (
                    resp.get("text")
                    or resp.get("output_text")
                    or resp.get("transcript")
                    or ""
                ).strip()
            except Exception:
                text = str(resp)
        cancel()
        logger.info(f"Voxtral transcription successful, text length: {len(text)}")
        return text
    except Exception as e:
        status_code = None
        response_body = None
        resp = getattr(e, "response", None)
        if resp is not None:
            status_code = getattr(resp, "status_code", None)
<<<<<<< HEAD
            response_body = getattr(resp, "text", None) or getattr(
                resp, "content", None
            )
=======
            response_body = getattr(resp, "text", None) or getattr(resp, "content", None)
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
            if response_body is None:
                try:
                    response_body = resp.json()
                except Exception:
                    response_body = None
        if status_code is None:
            status_code = getattr(e, "status_code", None)
        if response_body is None:
            response_body = getattr(e, "body", None)
        if isinstance(response_body, (bytes, bytearray)):
            try:
                response_body = response_body.decode("utf-8", errors="replace")
            except Exception:
                response_body = repr(response_body)
        if response_body is not None and len(str(response_body)) > 1000:
            response_body = f"{str(response_body)[:1000]}…"

        logger.warning(
            "Mistral transcription failed (status=%s, body=%s): %s",
            status_code,
            response_body,
            e,
            exc_info=True,
        )
        # Fallback: Gemini if available; otherwise empty string
        logger.error(f"Voxtral transcription failed: {type(e).__name__}: {e}")
        if getattr(settings, "GOOGLE_API_KEY", None):
            try:
                import google.generativeai as genai

                cancel()
                genai.configure(api_key=settings.GOOGLE_API_KEY)
                model = genai.GenerativeModel("gemini-1.5-flash")
                audio_inline = {
                    "inline_data": {
                        "mime_type": "audio/wav",
                        "data": base64.b64encode(wav_bytes).decode("utf-8"),
                    }
                }
                prompt = "Transcribe this audio. Return only the transcription text, no extra words."
                gresp = model.generate_content([{"text": prompt}, audio_inline])
                cancel()
                gemini_text = (gresp.text or "").strip()
                logger.info(
                    f"Gemini transcription successful, text length: {len(gemini_text)}"
                )
                return gemini_text
            except Exception as e2:
                logger.error(
                    f"Gemini transcription fallback also failed: {type(e2).__name__}: {e2}"
                )
                pass
        logger.warning("All transcription methods failed, returning empty string")
        return ""

<<<<<<< HEAD

=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
def generate_reply_from_audio(
    wav_bytes: bytes,
    hint_text: Optional[str] = None,
    cancel_check: Optional[CancelCallback] = None,
) -> str:
    """Use Voxtral chat with audio input to directly get a reply without separate STT.

    If Voxtral chat fails, fall back to transcribe + text generation.
    """
    cancel = _ensure_cancel(cancel_check)
    cancel()
    try:
        client = _client()
        audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": audio_b64},
                ],
            }
        ]
        # Include a short, safe hint to steer responses
        if hint_text and hint_text.strip():
            messages[0]["content"].append({"type": "text", "text": hint_text.strip()})
        else:
            messages[0]["content"].append(
                {"type": "text", "text": "Respond briefly as a safe DeFi mentor."}
            )

        cancel()
        resp = client.chat.complete(
            model="voxtral-mini-latest",
            messages=messages,
        )
        cancel()
        content = getattr(resp.choices[0].message, "content", resp.choices[0].message)
        if isinstance(content, list):
            text_parts: List[str] = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    text_parts.append(c.get("text", ""))
            out = " ".join([t for t in text_parts if t]).strip()
            if out:
                return out
        return str(content).strip()
    except Exception as e:
        logger.warning(f"Voxtral chat with audio failed; falling back to STT+LLM: {e}")
        # Fallback: STT then text generation
        try:
            text = transcribe_audio_with_voxtral(wav_bytes, cancel_check=cancel_check)
            if text:
                return generate_llm_reply(text, cancel_check=cancel_check)
        except Exception:
            pass
        return (
            "I couldn’t fully parse that audio. Could you repeat or speak a bit slower?"
        )


def generate_llm_reply(
    text: str,
    cancel_check: Optional[CancelCallback] = None,
    *,
    system_prompt: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> str:
    # Quick rule fallback for empty inputs
    if not text or not str(text).strip():
        return "I didn’t catch that. Could you rephrase your question about DeFi?"
    global _RESPONSES_AVAILABLE
    try:
        client = _client()
        cancel = _ensure_cancel(cancel_check)
        cancel()
        # Prefer Responses API when available; fallback to Chat API for older SDKs
        try:
            resp_iface = getattr(client, "responses", None)
            if resp_iface is not None:
                request_kwargs = {}
                if max_tokens is not None:
                    request_kwargs["max_tokens"] = max_tokens
                if temperature is not None:
                    request_kwargs["temperature"] = temperature
                r = resp_iface.create(
                    model="mistral-small-latest",
                    input=[
                        {
                            "role": "system",
                            "content": [
                                {
                                    "type": "text",
                                    "text": system_prompt
                                    or "You are Sophia, a concise and safe DeFi mentor. Keep replies under 50 words.",
                                }
                            ],
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Respond as a DeFi mentor to: {text}",
                                }
                            ],
                        },
                    ],
                    **request_kwargs,
                )
                cancel()
                out = getattr(r, "output_text", None)
                if isinstance(out, str) and out.strip():
                    return out.strip()
                return str(r)
<<<<<<< HEAD
        except Exception:
=======
        except Exception as responses_exc:
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
            pass

        # Chat API fallback
        cancel()
        chat_kwargs = {}
        if max_tokens is not None:
            chat_kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            chat_kwargs["temperature"] = temperature
        r2 = client.chat.complete(
            model="mistral-small-latest",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                    or "You are Sophia, a concise and safe DeFi mentor. Keep replies under 50 words.",
                },
                {"role": "user", "content": f"Respond as a DeFi mentor to: {text}"},
            ],
            **chat_kwargs,
        )
        cancel()
        content = getattr(r2.choices[0].message, "content", r2.choices[0].message)
        return str(content).strip()
    except Exception as e:
        # Log minimal detail for debugging
        try:
            import logging

            logging.getLogger("mistral").warning(f"Responses.create failed: {e}")
        except Exception:
            pass
        # Safe rule-based fallback
        lower = text.lower()
        if "yield" in lower:
            return "Yield farming can boost returns but carries risks like impermanent loss and smart-contract bugs. Start small and diversify."
        if "staking" in lower:
            return "Staking locks tokens to secure a network in exchange for rewards. Check lockups, slashing risk, and validator reputation."
        if "defi" in lower:
            return "DeFi lets you lend, borrow, and trade without banks. Always assess protocol audits, TVL, and team track record."
        return "Here’s a quick tip: manage risk with position sizing, avoid unaudited contracts, and never chase unsustainable APRs."

<<<<<<< HEAD

def generate_llm_reply_with_context(
    user_question: str,
    rag_context: str = "",
    emotion_label: str = "neutral",
    memory_context: str = "",
    intent: str = "small_talk",
) -> str:
    """Generate LLM reply with proper context separation."""

=======
def generate_llm_reply_with_context(
    user_question: str, 
    rag_context: str = "", 
    emotion_label: str = "neutral", 
    memory_context: str = "",
    intent: str = "small_talk"
) -> str:
    """Generate LLM reply with proper context separation."""
    
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    # Handle empty input first - before any logging that might crash
    if not user_question or not str(user_question).strip():
        logger.warning(f"⚠️ Empty user_question received with intent={intent}")
        if intent == "defi_question":
            return "I didn't catch that. Could you rephrase your question about DeFi?"
        elif intent == "emotional_support":
            return "I'm here to listen. What's on your mind?"
        else:
            return "I didn't catch that. Could you say that again?"
<<<<<<< HEAD

    # Log inputs for debugging (AFTER type guard to prevent crashes)
    logger.info("🎯 generate_llm_reply_with_context called:")
=======
    
    # Log inputs for debugging (AFTER type guard to prevent crashes)
    logger.info(f"🎯 generate_llm_reply_with_context called:")
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    logger.info(f"   user_question: '{user_question[:100]}'")
    logger.info(f"   intent: {intent}")
    logger.info(f"   emotion: {emotion_label}")
    logger.info(f"   rag_context length: {len(rag_context) if rag_context else 0}")
<<<<<<< HEAD
    logger.info(
        f"   memory_context length: {len(memory_context) if memory_context else 0}"
    )

    try:
        # Build system message with ALL context
        system_parts = []

        # Base personality
        system_parts.append(
            "You are Sophia, a knowledgeable and supportive DeFi education mentor."
        )

        # Add emotional context
        if emotion_label and emotion_label != "neutral":
            system_parts.append(
                f"\nUser's current emotional state: {emotion_label}. Be aware of this but prioritize factual accuracy."
            )

        # Add conversation history
        if memory_context:
            system_parts.append(f"\nConversation history: {memory_context}")

=======
    logger.info(f"   memory_context length: {len(memory_context) if memory_context else 0}")
    
    try:
        # Build system message with ALL context
        system_parts = []
        
        # Base personality  
        system_parts.append("You are Sophia, a knowledgeable and supportive DeFi education mentor.")
        
        # Add emotional context
        if emotion_label and emotion_label != "neutral":
            system_parts.append(f"\nUser's current emotional state: {emotion_label}. Be aware of this but prioritize factual accuracy.")
        
        # Add conversation history
        if memory_context:
            system_parts.append(f"\nConversation history: {memory_context}")
        
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        # Add RAG context
        if rag_context:
            system_parts.append(f"\n\nRELEVANT KNOWLEDGE BASE:\n{rag_context}")
            system_parts.append("\n⚠️ IMPORTANT: Use the knowledge base when relevant.")
<<<<<<< HEAD

        # Response guidelines based on intent
        system_parts.append("\n\nResponse guidelines:")
        if intent == "defi_question":
            system_parts.append(
                "- This is a DeFi educational question. Provide accurate answers (50-100 words)."
            )
        elif intent == "emotional_support":
            system_parts.append(
                "- Be empathetic while remaining educational (40-80 words)."
            )
        else:  # small_talk
            system_parts.append(
                "- This is casual conversation. Be friendly, warm, and conversational (20-40 words)."
            )
            system_parts.append(
                "- You can engage in general conversation, not just DeFi topics."
            )
            system_parts.append(
                "- If asked about yourself, share that you're Sophia, an AI assistant for DeFi education."
            )

        system_message = "".join(system_parts)

        logger.info(f"📝 System message built: {len(system_message)} chars")
        logger.info(f"📝 System message preview: {system_message[:200]}...")

        # User message is JUST the question
        client = _client()

        logger.info("🚀 Calling Mistral API...")

=======
        
        # Response guidelines based on intent
        system_parts.append("\n\nResponse guidelines:")
        if intent == "defi_question":
            system_parts.append("- This is a DeFi educational question. Provide accurate answers (50-100 words).")
        elif intent == "emotional_support":
            system_parts.append("- Be empathetic while remaining educational (40-80 words).")
        else:  # small_talk
            system_parts.append("- This is casual conversation. Be friendly, warm, and conversational (20-40 words).")
            system_parts.append("- You can engage in general conversation, not just DeFi topics.")
            system_parts.append("- If asked about yourself, share that you're Sophia, an AI assistant for DeFi education.")
        
        system_message = "".join(system_parts)
        
        logger.info(f"📝 System message built: {len(system_message)} chars")
        logger.info(f"📝 System message preview: {system_message[:200]}...")
        
        # User message is JUST the question
        client = _client()
        
        logger.info(f"🚀 Calling Mistral API...")
        
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        # Try Responses API first
        response_text = None
        try:
            resp_iface = getattr(client, "responses", None)
            if resp_iface is not None:
                logger.info("   Using Responses API")
                r = resp_iface.create(
                    model="mistral-large-latest",
                    input=[
                        {
                            "role": "system",
                            "content": [{"type": "text", "text": system_message}],
                        },
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": user_question}],
                        },
                    ],
                )
                out = getattr(r, "output_text", None)
<<<<<<< HEAD
                logger.info(
                    f"✅ Responses API returned: type={type(out)}, len={len(str(out)) if out else 0}"
                )
                logger.info(f"   Response preview: {str(out)[:200] if out else 'None'}")

=======
                logger.info(f"✅ Responses API returned: type={type(out)}, len={len(str(out)) if out else 0}")
                logger.info(f"   Response preview: {str(out)[:200] if out else 'None'}")
                
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
                if isinstance(out, str) and out.strip():
                    response_text = out.strip()
                else:
                    response_text = str(r)
<<<<<<< HEAD
                    logger.warning(
                        f"⚠️ output_text not found, using str(r): {response_text[:100]}"
                    )
        except Exception as e:
            logger.warning(f"⚠️ Responses API failed: {type(e).__name__}: {str(e)}")

=======
                    logger.warning(f"⚠️ output_text not found, using str(r): {response_text[:100]}")
        except Exception as e:
            logger.warning(f"⚠️ Responses API failed: {type(e).__name__}: {str(e)}")
        
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        # Chat API fallback
        if not response_text:
            logger.info("   Using Chat API (fallback)")
            r2 = client.chat.complete(
                model="mistral-large-latest",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_question},
                ],
            )
            content = getattr(r2.choices[0].message, "content", r2.choices[0].message)
            response_text = str(content).strip()
            logger.info(f"✅ Chat API returned: len={len(response_text)}")
            logger.info(f"   Response preview: {response_text[:200]}")
<<<<<<< HEAD

        logger.info(
            f"🎉 Mistral API SUCCESS - returning response: '{response_text[:100]}'"
        )
        return response_text

    except Exception as e:
        # ✅ ENHANCED ERROR LOGGING
        logger.error(f"❌ LLM with context failed: {type(e).__name__}: {str(e)}")

        # Check API key configuration
        settings = get_settings()
        has_key = bool(getattr(settings, "MISTRAL_API_KEY", None))
        key_length = len(settings.MISTRAL_API_KEY) if has_key else 0
        logger.error(
            f"🔑 MISTRAL_API_KEY status: present={has_key}, length={key_length}"
        )

        # Log API response details if available
        if hasattr(e, "response"):
            try:
                status = getattr(e.response, "status_code", "N/A")
                body = getattr(e.response, "text", "N/A")[:500]
                logger.error(f"📡 API Response Status: {status}")
                logger.error(f"📡 API Response Body: {body}")
            except Exception:
                pass

        # Log the full traceback for debugging
        import traceback

        logger.error(f"📋 Full traceback:\n{traceback.format_exc()}")

        # Context-aware rule-based fallback
        lower = user_question.lower()

        # Small talk fallbacks (NEW - based on intent)
        if intent == "small_talk":
            if any(
                greeting in lower
                for greeting in ["hello", "hi", "hey", "good morning", "good evening"]
            ):
=======
        
        logger.info(f"🎉 Mistral API SUCCESS - returning response: '{response_text[:100]}'")
        return response_text
        
    except Exception as e:
        # ✅ ENHANCED ERROR LOGGING
        logger.error(f"❌ LLM with context failed: {type(e).__name__}: {str(e)}")
        
        # Check API key configuration
        settings = get_settings()
        has_key = bool(getattr(settings, 'MISTRAL_API_KEY', None))
        key_length = len(settings.MISTRAL_API_KEY) if has_key else 0
        logger.error(f"🔑 MISTRAL_API_KEY status: present={has_key}, length={key_length}")
        
        # Log API response details if available
        if hasattr(e, 'response'):
            try:
                status = getattr(e.response, 'status_code', 'N/A')
                body = getattr(e.response, 'text', 'N/A')[:500]
                logger.error(f"📡 API Response Status: {status}")
                logger.error(f"📡 API Response Body: {body}")
            except:
                pass
        
        # Log the full traceback for debugging
        import traceback
        logger.error(f"📋 Full traceback:\n{traceback.format_exc()}")
        
        # Context-aware rule-based fallback
        lower = user_question.lower()
        
        # Small talk fallbacks (NEW - based on intent)
        if intent == "small_talk":
            if any(greeting in lower for greeting in ["hello", "hi", "hey", "good morning", "good evening"]):
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
                return "Hello! I'm Sophia, your DeFi education assistant. How can I help you today?"
            if "how are you" in lower or "how're you" in lower:
                return "I'm doing great, thanks for asking! I'm here to help you learn about DeFi. What would you like to know?"
            if "who are you" in lower or "what are you" in lower:
                return "I'm Sophia, an AI assistant specializing in DeFi education. I help people understand decentralized finance."
            if "your name" in lower or "you called" in lower:
                return "My name is Sophia. I'm here to help you navigate the world of DeFi!"
            # Generic small talk
<<<<<<< HEAD
            return (
                "I'm here to help! Feel free to ask me about DeFi, or we can just chat."
            )

=======
            return "I'm here to help! Feel free to ask me about DeFi, or we can just chat."
        
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        # DeFi-specific keywords
        if "yield" in lower:
            return "Yield farming can boost returns but carries risks like impermanent loss and smart-contract bugs. Start small and diversify."
        if "staking" in lower:
            return "Staking locks tokens to secure a network in exchange for rewards. Check lockups, slashing risk, and validator reputation."
        if "defi" in lower or "crypto" in lower:
            return "DeFi lets you lend, borrow, and trade without banks. Always assess protocol audits, TVL, and team track record."
<<<<<<< HEAD

        # Emotional support fallback
        if intent == "emotional_support":
            return "I understand you're going through something. Remember, it's okay to take a step back. I'm here for you."

        # Final generic fallback
        return "I'm here to help! What would you like to know?"


=======
        
        # Emotional support fallback
        if intent == "emotional_support":
            return "I understand you're going through something. Remember, it's okay to take a step back. I'm here for you."
        
        # Final generic fallback
        return "I'm here to help! What would you like to know?"

>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
def stream_generate_llm_reply(
    text: str,
    cancel_check: Optional[CancelCallback] = None,
):
    """Yield tokens from Mistral in a streaming fashion.

    This uses the Mistral Python SDK streaming API and yields plain text chunks
    as they arrive so the caller can forward them to clients immediately.
    """
    cancel = _ensure_cancel(cancel_check)
    cancel()

    def _extract_text_pieces(delta_content):
        """Normalize various SDK chunk formats into iterable text fragments."""
        if not delta_content:
            return []
        if isinstance(delta_content, str):
            return [delta_content]
        texts = []
        if isinstance(delta_content, list):
            for item in delta_content:
                if isinstance(item, str):
                    if item:
                        texts.append(item)
                    continue
                if isinstance(item, dict):
                    text_val = item.get("text")
                else:
                    text_val = getattr(item, "text", None)
                if text_val:
                    texts.append(text_val)
            return texts
        text_val = getattr(delta_content, "text", None)
        if text_val:
            return [text_val]
        text_repr = str(delta_content)
        if text_repr and text_repr != "None":
            return [text_repr]
        return []

    # Handle empty input before attempting API
    if not text or not str(text).strip():
        yield "I didn't catch that. Could you say that again?"
        return
    cancel()
    client = _client()

    # Use Chat streaming with proper error handling
    try:
        logger.info(f"Starting streaming LLM reply for text: {text[:50]}...")

        stream = client.chat.stream(
            model="mistral-large-latest",
            messages=[
                {
                    "role": "system",
                    "content": "You are Sophia, a concise and safe DeFi mentor. Keep replies under 50 words.",
                },
                {"role": "user", "content": f"Respond as a DeFi mentor to: {text}"},
            ],
        )
        cancel()

        tokens_yielded = 0
        for event in stream:
            cancel()
            try:
                chunk = getattr(event, "data", event)

                choices = getattr(chunk, "choices", None)
                if choices:
                    for choice in choices:
                        delta = getattr(choice, "delta", None)
                        if not delta:
                            continue
                        for piece in _extract_text_pieces(
                            getattr(delta, "content", None)
                        ):
                            cancel()
                            yield piece
                            tokens_yielded += 1
                    continue

                delta = getattr(chunk, "delta", None)
                if delta:
                    for piece in _extract_text_pieces(getattr(delta, "content", None)):
                        cancel()
                        yield piece
                        tokens_yielded += 1
                    continue

                content = getattr(chunk, "content", None)
                for piece in _extract_text_pieces(
                    content if content is not None else chunk
                ):
                    cancel()
                    yield piece
                    tokens_yielded += 1
            except Exception as e:
                logger.warning(f"Error processing stream chunk: {e}")
                continue

        cancel()
        logger.info(f"Streaming completed, yielded {tokens_yielded} tokens")

        if tokens_yielded == 0:
            logger.warning(
                "No tokens were yielded from stream, falling back to rule-based response"
            )
            # Fallback to rule-based response if streaming failed
            lower = text.lower()
            if "yield" in lower:
                cancel()
                yield "Yield farming can boost returns but carries risks like impermanent loss and smart-contract bugs. Start small and diversify."
            elif "staking" in lower:
                cancel()
                yield "Staking locks tokens to secure a network in exchange for rewards. Check lockups, slashing risk, and validator reputation."
            elif "defi" in lower:
                cancel()
                yield "DeFi lets you lend, borrow, and trade without banks. Always assess protocol audits, TVL, and team track record."
            else:
                cancel()
                yield "Here's a quick tip: manage risk with position sizing, avoid unaudited contracts, and never chase unsustainable APRs."

    except Exception as e:
        logger.error(f"Streaming LLM reply failed: {e}")
        # Final rule fallback
        lower = text.lower()
        if "yield" in lower:
            cancel()
            yield "Yield farming can boost returns but carries risks like impermanent loss and smart-contract bugs. Start small and diversify."
        elif "staking" in lower:
            cancel()
            yield "Staking locks tokens to secure a network in exchange for rewards. Check lockups, slashing risk, and validator reputation."
        elif "defi" in lower:
            cancel()
            yield "DeFi lets you lend, borrow, and trade without banks. Always assess protocol audits, TVL, and team track record."
        else:
            cancel()
            yield "Here's a quick tip: manage risk with position sizing, avoid unaudited contracts, and never chase unsustainable APRs."


def stream_generate_reply_from_audio(
    wav_bytes: bytes,
    cancel_check: Optional[CancelCallback] = None,
):
    """Stream tokens directly from Voxtral using audio input + chat completion.

    This bypasses separate STT and uses Voxtral's native audio understanding
    with streaming for the fastest possible response times.
    """
    cancel = _ensure_cancel(cancel_check)
    cancel()
    try:
        client = _client()
        audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
        cancel()

        logger.info("Starting Voxtral audio streaming...")

        stream = client.chat.stream(
            model="voxtral-mini-latest",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": audio_b64,
                        },
                        {
                            "type": "text",
                            "text": "Respond briefly as Sophia, a safe DeFi mentor. Keep under 50 words.",
                        },
                    ],
                }
            ],
        )

        tokens_yielded = 0
        for chunk in stream:
            cancel()
            try:
                # Handle CompletionEvent wrapper from newer Mistral SDK
                if hasattr(chunk, "data"):
                    chunk_data = chunk.data
                else:
                    chunk_data = chunk

                # Handle different chunk formats from Mistral SDK
                if hasattr(chunk_data, "choices") and chunk_data.choices:
                    delta = chunk_data.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        cancel()
                        yield delta.content
                    tokens_yielded += 1
                elif hasattr(chunk_data, "delta") and chunk_data.delta:
                    if (
                        hasattr(chunk_data.delta, "content")
                        and chunk_data.delta.content
                    ):
                        cancel()
                        yield chunk_data.delta.content
                    tokens_yielded += 1
                elif hasattr(chunk_data, "content") and chunk_data.content:
                    cancel()
                    yield chunk_data.content
                tokens_yielded += 1
            except Exception as e:
                logger.warning(f"Error processing Voxtral stream chunk: {e}")
                continue

        logger.info(f"Voxtral streaming completed, yielded {tokens_yielded} tokens")

        if tokens_yielded == 0:
            logger.warning(
                "No tokens from Voxtral stream, falling back to STT + text streaming"
            )
            # Fallback to traditional STT + text streaming
            try:
                text = transcribe_audio_with_voxtral(wav_bytes)
                if text:
                    for token in stream_generate_llm_reply(text):
                        cancel()
                        yield token
                else:
                    yield "I couldn't understand the audio. Could you try speaking more clearly?"
            except Exception:
                yield "I'm having trouble processing audio right now. Please try again."

    except Exception as e:
        logger.error(f"Voxtral audio streaming failed: {e}")
        # Fallback to traditional STT + text streaming
        try:
            text = transcribe_audio_with_voxtral(wav_bytes)
            if text:
                for token in stream_generate_llm_reply(text):
                    cancel()
                    yield token
            else:
                yield "I couldn't understand the audio. Could you try speaking more clearly?"
        except Exception:
            yield "I'm having trouble processing audio right now. Please try again."
