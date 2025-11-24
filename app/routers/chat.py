"""Chat and voice endpoints."""

import asyncio
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, Sequence

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    Request,
)
from fastapi.responses import StreamingResponse
from app.routers.audio_receiver import receive_audio_chunks
from opentelemetry import trace
from slowapi.errors import RateLimitExceeded

from app.helpers import extract_audio, sse_event, validate_audio_upload
from app.audio_utils import avg_abs_pcm16, pcm16_to_wav, wav_header_pcm16
from app.deps import (
    verify_api_key,
    limiter,
    require_consent,
    extract_identity_from_token,
)
from app.schemas.chat import (
    ChatResponse,
    DefiChatResponse,
    Emotion,
    GenerateRequest,
    GenerateResponse,
    SynthesizeRequest,
    SynthesizeResponse,
    TextChatRequest,
    TranscriptionResponse,
)
from app.services import supabase as supabase_service
from app.services.audio_queue import get_audio_queue_manager, AudioSegment
from app.services.langgraph_service import langgraph_service
from app.services.shared_services import shared_services
from app.services.emotional_guidance import build_emotion_guided_prompt
from app.services.memory import memory_manager, ConversationTurn
from app import chat as chat_service
from app.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()



async def _ws_send_json(ws: WebSocket, obj: dict) -> None:
    import json as _json

    await ws.send_text(_json.dumps(obj))


@asynccontextmanager
async def manage_session_turn(
    session_id: str, *, metadata: Optional[Dict[str, Any]] = None
):
    """Acquire a per-session turn and ensure it is released safely."""
    manager = shared_services.get_session_turn_manager()
    state = await manager.start_turn(session_id, metadata=metadata)
    try:
        yield state
        if manager.get_turn(state.turn_id) is not None:
            await manager.finish_turn(state.turn_id, status="completed")
    except asyncio.CancelledError:
        if manager.get_turn(state.turn_id) is not None:
            await manager.finish_turn(state.turn_id, status="cancelled")
        raise
    except Exception as exc:
        if manager.get_turn(state.turn_id) is not None:
            await manager.fail_turn(state.turn_id, exc)
        raise


@router.websocket("/ws/voice")
async def ws_voice(websocket: WebSocket):
    """WebSocket pipeline with VAD-driven barge-in and queued audio playback."""

    api_key = websocket.query_params.get("token") or websocket.headers.get(
        "Authorization"
    )

    if api_key and not api_key.lower().startswith("bearer "):
        api_key = f"Bearer {api_key}"

    try:
        logger.info("🔑 Attempting to verify API key...")
        supabase_token = verify_api_key(authorization=api_key)
        logger.info("✅ API key verified successfully")
    except HTTPException as exc:
        logger.error(f"❌ API key verification failed: {exc.detail}")
        await websocket.close(code=1008, reason=exc.detail)
        return

    supabase_user_id, discord_id = extract_identity_from_token(supabase_token)

    logger.info(
        f"🔌 WebSocket /ws/voice request: discord_id={discord_id}, has_token={bool(api_key)}"
    )

    try:
        require_consent(
            request=None, discord_id=discord_id, supabase_token=supabase_token
        )
    except HTTPException as exc:
        await websocket.close(code=1008, reason=exc.detail)
        return

    logger.info("🎉 WebSocket connection accepted!")
    await websocket.accept()
    SAMPLE_RATE = 16000
    BYTES_PER_SEC = SAMPLE_RATE * 2  # pcm16 mono
    SILENCE_THRESHOLD = 300
    SILENCE_MS = 600
    SILENCE_BYTES = int(BYTES_PER_SEC * (SILENCE_MS / 1000.0))
    last_final_text = ""
    last_reply_text = ""
    last_audio_url: Optional[str] = None

    session_id = str(uuid.uuid4())
    audio_queue = get_audio_queue_manager()
    manager = shared_services.get_session_turn_manager()
    metadata: Dict[str, Any] = {"endpoint": "/ws/voice"}
    if discord_id:
        metadata["discord_id"] = discord_id

    async def send_audio_callback(segment: AudioSegment):
        import base64 as _b64

        eos = bool(segment.metadata.get("eos"))
        turn_id = segment.metadata.get("turn_id")
        payload_bytes = segment.audio_data or b""
        mime = segment.mime_type or "audio/mpeg"

        if payload_bytes:
            has_wav_header = payload_bytes[:4] == b"RIFF"
            if has_wav_header:
                mime = "audio/wav"
            elif mime in {"audio/pcm", "audio/x-raw"}:
                sample_rate = int(segment.metadata.get("sample_rate", 48000))
                payload_bytes = pcm16_to_wav(payload_bytes, sample_rate=sample_rate)
                mime = "audio/wav"

        b64_data = (
            _b64.b64encode(payload_bytes).decode("ascii") if payload_bytes else ""
        )
        await _ws_send_json(
            websocket,
            {
                "type": "audio_chunk",
                "mime": mime,
                "b64": b64_data,
                "eos": eos,
                "turn_id": turn_id,
            },
        )

    await audio_queue.start_playback(session_id, send_audio_callback)

    async def barge_in_calback(barge_in_ms, current_cancelled, queue_cleared, interrupted_turn_id):
        try:
            await _ws_send_json(
                websocket,
                {
                    "type": "barge_in",
                    "interruption_ms": barge_in_ms,
                    "cancelled": current_cancelled,
                    "cleared": queue_cleared,
                    "interrupted_turn_id": interrupted_turn_id,
                },
            )
        except:
            logger.warning('Failed to send barge-in notification')

    try:
        in_speech = asyncio.Event()
        async for wav_utter in receive_audio_chunks(
            websocket,
            session_id,
            in_speech,
            manager,
            audio_queue,
            barge_in_calback
        ):
            logger.info(f'Got {len(wav_utter)} audio bytes')
            async with manage_session_turn(
                session_id, metadata=metadata
            ) as turn_state:

                def cancel_check():
                    manager.raise_if_cancelled(turn_state.turn_id)

                reply_tokens: list[str] = []
                tokens_sent = 0
                turn_state.set_status("streaming")
                try:
                    async for (
                        tok
                    ) in langgraph_service.stream_conversation_response(
                        wav_utter
                    ):
                        cancel_check()
                        if not tok:
                            continue
                        if isinstance(tok, dict) and tok.get("__tier0__"):
                            await _ws_send_json(
                                websocket, {"type": "tier0_result", **tok}
                            )
                            logger.info(
                                f"📤 Sent tier-0 result to frontend: intent={tok.get('intent')}, emotion={tok.get('emotion')}"
                            )
                            continue
                        reply_tokens.append(tok)
                        await _ws_send_json(
                            websocket,
                            {
                                "type": "token",
                                "text": tok,
                                "turn_id": turn_state.turn_id,
                            },
                        )
                        tokens_sent += 1
                except Exception as exc:
                    logger.warning(f"WS: LangGraph streaming failed: {exc}")

                if tokens_sent == 0:
                    fallback_response = "I'm here to help with DeFi questions. Could you please repeat your question?"
                    for i in range(0, len(fallback_response), 8):
                        chunk_text = fallback_response[i : i + 8]
                        reply_tokens.append(chunk_text)
                        await _ws_send_json(
                            websocket,
                            {
                                "type": "token",
                                "text": chunk_text,
                                "turn_id": turn_state.turn_id,
                            },
                        )
                        tokens_sent += 1

                reply_full = "".join(reply_tokens).strip() or "Okay."
                await _ws_send_json(
                    websocket,
                    {
                        "type": "reply_done",
                        "text": reply_full,
                        "turn_id": turn_state.turn_id,
                    },
                )

                turn_state.set_status("synthesizing")
                sentences = [
                    s.strip()
                    for s in re.split(r"(?<=[\.!?])\s+", reply_full)
                    if s.strip()
                ]
                audio_url_last = None
                for idx, sent in enumerate(sentences):
                    streamed_any = False
                    try:
                        for pcm_chunk in chat_service.synthesize_streamed_reply(
                            sent, 48000, cancel_check
                        ):
                            streamed_any = True
                            await audio_queue.enqueue(
                                session_id=session_id,
                                audio_data=pcm_chunk,
                                mime_type="audio/pcm",
                                metadata={
                                    "turn_id": turn_state.turn_id,
                                    "sentence": sent,
                                    "chunk_index": idx,
                                    "eos": False,
                                    "sample_rate": 48000,
                                },
                            )
                    except Exception:
                        logger.exception(
                            "WS: streaming TTS failed; falling back to full synthesis"
                        )

                    if not streamed_any:
                        try:
                            (
                                audio_bytes,
                                audio_url_last,
                            ) = chat_service.synthesize_reply(
                                sent, cancel_check
                            )
                            cancel_check()
                            await audio_queue.enqueue(
                                session_id=session_id,
                                audio_data=audio_bytes,
                                mime_type="audio/mpeg",
                                metadata={
                                    "turn_id": turn_state.turn_id,
                                    "sentence": sent,
                                    "chunk_index": idx,
                                    "eos": False,
                                },
                            )
                            await _ws_send_json(
                                websocket,
                                {
                                    "type": "audio_url_chunk",
                                    "audio_url": audio_url_last,
                                    "turn_id": turn_state.turn_id,
                                },
                            )
                        except Exception:
                            logger.exception(
                                "WS: fallback TTS synthesis failed"
                            )

                await audio_queue.enqueue(
                    session_id=session_id,
                    audio_data=b"",
                    mime_type="audio/pcm",
                    metadata={
                        "turn_id": turn_state.turn_id,
                        "eos": True,
                        "sample_rate": 48000,
                    },
                )
                if audio_url_last is None:
                    try:
                        cancel_check()
                        audio_bytes, audio_url_last = chat_service.synthesize_reply(
                            reply_full, cancel_check=cancel_check
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        logger.warning(
                            "WS: failed to synthesize/upload archival audio for reply"
                        )

                await _ws_send_json(
                    websocket,
                    {
                        "type": "audio_url",
                        "audio_url": audio_url_last,
                        "turn_id": turn_state.turn_id,
                    },
                )

                last_final_text = f"[Audio processed: {len(wav_utter)} bytes]"
                last_reply_text = reply_full
                last_audio_url = audio_url_last
                turn_state.set_status("completed")
            in_speech.clear()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await _ws_send_json(websocket, {"type": "error", "detail": str(exc)})
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        try:
            stats = audio_queue.get_stats(session_id)
            if stats:
                logger.info(
                    f"WS Session {session_id}: stats played={stats.segments_played}, "
                    f"cancelled={stats.segments_cancelled}, "
                    f"total_cancellations={stats.total_cancellations}, "
                    f"last_interrupt_ms={stats.last_interruption_ms}"
                )
            await audio_queue.cleanup_session(session_id)
        except Exception as exc:
            logger.warning(f"WS Session {session_id}: cleanup error: {exc}")

    try:
        if last_final_text or last_reply_text:
            supabase_service.insert_conversation_session(
                {
                    "transcript": last_final_text,
                    "reply": last_reply_text,
                    "audio_url": last_audio_url or None,
                    "user_id": supabase_user_id,
                },
                access_token=supabase_token,
            )
    except Exception:
        pass


@router.post("/transcribe", response_model=TranscriptionResponse)
@limiter.limit(settings.API_RATE_LIMIT)
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    supabase_token: str = Depends(verify_api_key),
):
    validate_audio_upload(file)
    wav_bytes = await extract_audio(file)

    session_id = uuid.uuid4()

    text = chat_service.transcript_audio(wav_bytes)
    user_emotion, _ = chat_service.analyze_emotion_by_audio(wav_bytes, role="user")
    supabase_user_id, _ = extract_identity_from_token(supabase_token)

    try:
        supabase_service.insert_emotion_score(
            session_id,
            role="user",
            emotion=user_emotion,
            user_id=supabase_user_id,
            access_token=supabase_token,
        )
    except Exception:
        logger.warning("Failed to persist user emotion score; continuing")

    return TranscriptionResponse(text=text, emotion=user_emotion.model_dump())


@router.post("/generate-response", response_model=GenerateResponse)
@limiter.limit(settings.API_RATE_LIMIT)
async def generate_response(
    request: Request,
    body: GenerateRequest,
    supabase_token: str = Depends(verify_api_key),
):
    reply = chat_service.generate_llm_reply(body.text)
    return GenerateResponse(reply=reply, tone="encouraging")


@router.post("/generate-response/stream")
@limiter.limit(settings.API_RATE_LIMIT)
async def generate_response_stream(
    request: Request,
    body: GenerateRequest,
    supabase_token: str = Depends(verify_api_key),
):
    """Stream LLM tokens as they are generated."""
    try:
        generator = chat_service.generate_streamed_llm_reply(body.text)
        return StreamingResponse(generator, media_type="text/plain")
    except Exception:
        logger.exception("Streaming response generation failed")
        raise HTTPException(
            status_code=500, detail="Streaming response generation failed"
        )


@router.post("/synthesize", response_model=SynthesizeResponse)
@limiter.limit(settings.API_RATE_LIMIT)
async def synthesize(
    request: Request,
    body: SynthesizeRequest,
    supabase_token: str = Depends(verify_api_key),
):
    supabase_user_id, _ = extract_identity_from_token(supabase_token)

    audio_bytes, audio_url = chat_service.synthesize_reply(body.text)
    sophia_emotion, _ = chat_service.analyze_emotion_by_audio(
        audio_bytes, role="sophia"
    )

    try:
        session_id = uuid.uuid4()
        supabase_service.insert_emotion_score(
            session_id,
            role="sophia",
            emotion=sophia_emotion,
            user_id=supabase_user_id,
            access_token=supabase_token,
        )
    except Exception:
        logger.warning("Failed to persist sophia emotion score; continuing")

    return SynthesizeResponse(audio_url=audio_url, emotion=sophia_emotion.model_dump())


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.API_RATE_LIMIT)
async def chat(
    request: Request,
    file: UploadFile = File(...),
    supabase_token: str = Depends(verify_api_key),
    consent_ok: None = Depends(require_consent),
):
    validate_audio_upload(file)
    wav_bytes = await extract_audio(file)

    supabase_user_id, discord_id = extract_identity_from_token(supabase_token)
    manager = shared_services.get_session_turn_manager()

    session_uuid = uuid.uuid4()
    session_id_str = str(session_uuid)
    metadata: Dict[str, Any] = {"endpoint": "/chat"}
    if discord_id:
        metadata["discord_id"] = discord_id

    async with manage_session_turn(session_id_str, metadata=metadata) as turn_state:

        def cancel_check():
            manager.raise_if_cancelled(turn_state.turn_id)

        current_span = trace.get_current_span()
        current_span.set_attribute("session.id", session_id_str)
        t0 = time.time()

        transcript = chat_service.transcript_audio(wav_bytes, cancel_check)

        cancel_check()

        user_emotion, _ = chat_service.analyze_emotion_by_audio(
            wav_bytes, cancel_check, role="user"
        )

        turn_state.set_status("streaming")
        cancel_check()

        reply = chat_service.generate_llm_reply(transcript, cancel_check)

        turn_state.set_status("synthesizing")
        cancel_check()

        reply_audio_bytes, audio_url = chat_service.synthesize_reply(
            reply, cancel_check
        )

        sophia_emotion, _ = chat_service.analyze_emotion_by_audio(
            reply_audio_bytes, cancel_check, role="sophia"
        )

        total_ms = int((time.time() - t0) * 1000)
        current_span.set_attribute("total_roundtrip_time.ms", total_ms)
        current_span.set_attribute("phoenix_user_emotion.label", user_emotion.label)
        current_span.set_attribute(
            "phoenix_user_emotion.confidence", float(user_emotion.confidence)
        )
        current_span.set_attribute("phoenix_sophia_emotion.label", sophia_emotion.label)
        current_span.set_attribute(
            "phoenix_sophia_emotion.confidence", float(sophia_emotion.confidence)
        )

        chat_service.persist_conversation_session(
            session_id=session_uuid,
            transcript=transcript,
            reply=reply,
            user_emotion=user_emotion,
            sophia_emotion=sophia_emotion,
            reply_audio_url=audio_url,
            user_id=supabase_user_id,
            supabase_token=supabase_token,
        )

        turn_state.set_status("completed")
        return ChatResponse(
            transcript=transcript,
            reply=reply,
            user_emotion=user_emotion.model_dump(),
            sophia_emotion=sophia_emotion.model_dump(),
            audio_url=audio_url,
        )


@router.post("/defi-chat", response_model=DefiChatResponse)
@limiter.limit(settings.API_RATE_LIMIT)
async def defi_chat(
    request: Request,
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
    supabase_token: str = Depends(verify_api_key),
    consent_ok: None = Depends(require_consent),
):
    validate_audio_upload(file)
    wav_bytes = await extract_audio(file)

    user_id, discord_id = extract_identity_from_token(supabase_token)

    session_identifier = session_id or str(uuid.uuid4())
    metadata: Dict[str, Any] = {"endpoint": "/defi-chat"}
    if session_id:
        metadata["provided_session_id"] = session_id
    if discord_id:
        metadata["discord_id"] = discord_id
    manager = shared_services.get_session_turn_manager()

    async with manage_session_turn(session_identifier, metadata=metadata) as turn_state:

        def cancel_check():
            manager.raise_if_cancelled(turn_state.turn_id)

        try:
            cancel_check()

            turn_state.set_status("streaming")
            cancel_check()
            result = langgraph_service.process_conversation(
                audio_bytes=wav_bytes,
                session_id=session_identifier,
                collect_evaluation_data=True,
                supabase_token=supabase_token,
                cancel_check=cancel_check,
            )

            turn_state.set_status("synthesizing")
            cancel_check()

            chat_service.persist_conversation_session(
                supabase_token=supabase_token,
                user_id=user_id,
                session_id=result["session_id"],
                transcript=result["transcript"],
                reply=result["reply"],
                user_emotion=Emotion(
                    label=result["user_emotion"]["label"],
                    confidence=result["user_emotion"]["confidence"],
                ),
                sophia_emotion=Emotion(
                    label=result["sophia_emotion"]["label"],
                    confidence=result["sophia_emotion"]["confidence"],
                ),
                reply_audio_url=result.get("audio_url"),
                intent=result["intent"],
                context_memory=str(result["context_memory"]),
            )

            turn_state.set_status("completed")
            return DefiChatResponse(**result)

        except asyncio.CancelledError:
            logger.info("DeFi chat turn %s cancelled", turn_state.turn_id)
            raise
        except Exception as e:
            logger.exception("DeFi chat processing failed")
            raise HTTPException(
                status_code=500, detail=f"DeFi chat processing failed: {str(e)}"
            )


@router.post("/defi-chat/stream")
@limiter.limit(settings.API_RATE_LIMIT)
async def defi_chat_stream(
    request: Request,
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
    supabase_token: str = Depends(verify_api_key),
    consent_ok: None = Depends(require_consent),
):
    """Streaming variant of DeFi chat."""
    validate_audio_upload(file)
    wav_bytes = await extract_audio(file)

    user_id, discord_id = extract_identity_from_token(supabase_token)
    session_identifier = session_id or str(uuid.uuid4())
    metadata: Dict[str, Any] = {"endpoint": "/defi-chat/stream"}
    if session_identifier:
        metadata["provided_session_id"] = session_identifier
    if discord_id:
        metadata["discord_id"] = discord_id
    manager = shared_services.get_session_turn_manager()

    async def event_generator():
        nonlocal session_identifier
        async with manage_session_turn(
            session_identifier, metadata=metadata
        ) as turn_state:

            def cancel_check():
                manager.raise_if_cancelled(turn_state.turn_id)

            try:
                cancel_check()
                transcript = chat_service.transcript_audio(wav_bytes, cancel_check)
                cancel_check()
                user_emotion, _ = chat_service.analyze_emotion_by_audio(
                    wav_bytes, cancel_check, role="user"
                )

                yield sse_event(
                    "transcript",
                    {
                        "transcript": transcript,
                        "user_emotion": user_emotion.model_dump(),
                        "session_id": session_identifier,
                    },
                )

                turn_state.set_status("streaming")
                reply_accum = []
                for chunk in chat_service.generate_streamed_llm_reply(
                    transcript,
                    cancel_check=cancel_check,
                ):
                    reply_accum.append(chunk)
                    safe_chunk = chunk.replace("\n", " ")
                    yield sse_event("token", safe_chunk)

                reply = "".join(reply_accum).strip()
                yield sse_event("reply_done", {"reply": reply})

                turn_state.set_status("synthesizing")
                cancel_check()

                audio_bytes, audio_url = chat_service.synthesize_reply(
                    reply, cancel_check
                )

                cancel_check()
                sophia_emotion, mock_audio = chat_service.analyze_emotion_by_audio(
                    audio_bytes, cancel_check, role="sophia"
                )

                cancel_check()
                chat_service.persist_conversation_session(
                    session_id=session_identifier,
                    transcript=transcript,
                    reply=reply,
                    user_emotion=user_emotion,
                    sophia_emotion=sophia_emotion,
                    reply_audio_url=audio_url,
                    user_id=user_id,
                    supabase_token=supabase_token,
                )

                turn_state.set_status("completed")

                payload = {
                    "audio_url": audio_url,
                    "sophia_emotion": (
                        sophia_emotion.model_dump() if sophia_emotion else None
                    ),
                    "mock_audio": mock_audio,
                }
                yield sse_event("audio_url", payload)

            except asyncio.CancelledError:
                logger.info("Streaming DeFi chat turn %s cancelled", turn_state.turn_id)
                raise
            except Exception as e:
                logger.exception("Streaming DeFi chat failed")
                yield sse_event("error", {"detail": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/text-chat", response_model=DefiChatResponse)
@limiter.limit(settings.API_RATE_LIMIT)
async def text_chat(
    request: Request,
    body: TextChatRequest,
    supabase_token: str = Depends(verify_api_key),
    consent_ok: None = Depends(require_consent),
):
    """Text-only chat endpoint for DeFi conversations."""
    user_id, discord_id = extract_identity_from_token(supabase_token)

    session_identifier = body.session_id or str(uuid.uuid4())
    metadata: Dict[str, Any] = {"endpoint": "/text-chat"}
    if body.session_id:
        metadata["provided_session_id"] = body.session_id
    if discord_id:
        metadata["discord_id"] = discord_id

    manager = shared_services.get_session_turn_manager()

    async with manage_session_turn(session_identifier, metadata=metadata) as turn_state:

        def cancel_check():
            manager.raise_if_cancelled(turn_state.turn_id)

        try:
            turn_state.set_status("streaming")
            cancel_check()
            result = langgraph_service.process_text_conversation(
                message=body.message,
                session_id=session_identifier,
                collect_evaluation_data=True,
                supabase_token=supabase_token,
                cancel_check=cancel_check,
            )

            turn_state.set_status("synthesizing")
            cancel_check()

            chat_service.persist_conversation_session(
                supabase_token=supabase_token,
                user_id=user_id,
                session_id=result["session_id"],
                transcript=result["transcript"],
                reply=result["reply"],
                user_emotion=Emotion(
                    label=result["user_emotion"]["label"],
                    confidence=result["user_emotion"]["confidence"],
                ),
                sophia_emotion=Emotion(
                    label=result["sophia_emotion"]["label"],
                    confidence=result["sophia_emotion"]["confidence"],
                ),
                reply_audio_url=result.get("audio_url"),
                intent=result["intent"],
                context_memory=str(result["context_memory"]),
            )

            turn_state.set_status("completed")
            return DefiChatResponse(**result)

        except asyncio.CancelledError:
            logger.info("Text chat turn %s cancelled", turn_state.turn_id)
            raise
        except Exception as e:
            logger.exception("Text chat processing failed")
            raise HTTPException(
                status_code=500, detail=f"Text chat processing failed: {str(e)}"
            )


def _record_text_stream_turn(
    session_id: str,
    user_text: str,
    reply: str,
    user_emotion: Dict[str, Any],
    sophia_emotion: Optional[Emotion],
    supabase_token: Optional[str],
):
    try:
        turn = ConversationTurn(
            query=user_text,
            response=reply,
            user_emotion=user_emotion.get("label") or "neutral",
            sophia_emotion=getattr(sophia_emotion, "label", "neutral"),
            intent="text_chat",
            timestamp=time.time(),
        )
        memory_manager.update_session_memory(
            session_id, turn, access_token=supabase_token
        )
    except Exception as exc:
        logger.warning("Text chat stream memory update failed: %s", exc)


@router.post("/text-chat/stream")
@limiter.limit(settings.API_RATE_LIMIT)
async def text_chat_stream(
    request: Request,
    body: TextChatRequest,
    supabase_token: str = Depends(verify_api_key),
    consent_ok: None = Depends(require_consent),
):
    """Streaming variant for text-only chat."""
    user_id, discord_id = extract_identity_from_token(supabase_token)
    session_identifier = body.session_id or str(uuid.uuid4())
    metadata: Dict[str, Any] = {"endpoint": "/text-chat/stream"}
    if body.session_id:
        metadata["provided_session_id"] = body.session_id
    if discord_id:
        metadata["discord_id"] = discord_id
    manager = shared_services.get_session_turn_manager()

    async def event_generator():
        async with manage_session_turn(
            session_identifier, metadata=metadata
        ) as turn_state:

            def cancel_check():
                manager.raise_if_cancelled(turn_state.turn_id)

            try:

                result = langgraph_service.process_text_conversation(
                    body.message,
                    session_identifier,
                    collect_evaluation_data=True,
                    supabase_token=supabase_token,
                    cancel_check=cancel_check
                )
                yield sse_event('token', result['reply'].replace('\n', ' '))
                yield sse_event('reply_done', {
                    'reply': result['reply'],
                    'user_emotion': result['user_emotion']
                })
                yield sse_event('audio_url', {
                    "audio_url": result.get('audio_url'),
                    "sophia_emotion": result['sophia_emotion'],
                    "mock_audio": result['is_mock_audio'],
                    "user_emotion": result['user_emotion'],
                })

                # user_emotion = chat_service.analyze_emotion_by_text(body.message)
                # flash_context = memory_manager.get_context_for_llm(
                #     session_identifier, access_token=supabase_token
                # )
                # guided_prompt = chat_service.get_enriched_prompt(
                #     body.message,
                #     user_emotion,
                #     flash_context
                # )

                # turn_state.set_status("streaming")
                # reply_accum = []
                # for chunk in chat_service.generate_streamed_llm_reply(
                #     guided_prompt,
                #     cancel_check=cancel_check,
                # ):
                #     reply_accum.append(chunk)
                #     safe_chunk = chunk.replace("\n", " ")
                #     yield sse_event("token", safe_chunk)

                # reply = "".join(reply_accum).strip()
                # reply_payload = {
                #     "reply": reply,
                #     "user_emotion": user_emotion.model_dump(),
                # }
                # yield sse_event("reply_done", reply_payload)

                # turn_state.set_status("synthesizing")
                # cancel_check()

                # audio_bytes, audio_url = chat_service.synthesize_reply(
                #     reply, cancel_check
                # )
                # cancel_check()
                # sophia_emotion, mock_audio = chat_service.analyze_emotion_by_audio(
                #     audio_bytes, cancel_check, role="sophia"
                # )

                # payload = {
                #     "audio_url": audio_url,
                #     "sophia_emotion": (
                #         sophia_emotion.model_dump() if sophia_emotion else None
                #     ),
                #     "mock_audio": mock_audio,
                #     "user_emotion": user_emotion.model_dump(),
                # }

                _record_text_stream_turn(
                    session_identifier,
                    body.message,
                    result['reply'],
                    result['user_emotion'],
                    result['sophia_emotion'],
                    supabase_token,
                )

                turn_state.set_status("completed")

            except asyncio.CancelledError:
                logger.info("Streaming text chat turn %s cancelled", turn_state.turn_id)
                raise
            except Exception as e:
                logger.exception("Streaming text chat failed")
                yield sse_event("error", {"detail": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
