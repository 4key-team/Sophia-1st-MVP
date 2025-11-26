"""FastAPI entry point that wires endpoints, middleware, telemetry, and voice pipelines."""

import os
<<<<<<< HEAD
import time
import logging
from typing import Sequence

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.config import get_settings
from app.config_validation import validate_settings
from app.deps import verify_api_key, limiter
from app.services import supabase as supabase_service
from app.tracing import setup_tracer
from app.routers import (
    chat as chat_router,
    admin as admin_router,
    evaluation as evaluation_router,
)
from dotenv import load_dotenv

=======
import asyncio
import time
import uuid
import logging
from contextlib import asynccontextmanager
from typing import Optional, Sequence, Any, Dict

from fastapi import (
    FastAPI,
    File,
    UploadFile,
    HTTPException,
    Depends,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.config import get_settings
from app.config_validation import validate_settings
from app.deps import (
    verify_api_key,
    limiter,
    require_consent,
    extract_identity_from_token,
)
from app.services import mistral as mistral_service
from app.services.langgraph_service import langgraph_service
from app.services.emotion import analyze_emotion_audio, infer_text_emotion
from app.services.tts import synthesize_inworld, synthesize_inworld_stream
from app.services import supabase as supabase_service
from app.services.audio_queue import get_audio_queue_manager, AudioSegment
from app.services.shared_services import shared_services
from app.services.emotional_guidance import (
    get_guidance as get_emotional_guidance,
    build_emotion_guided_prompt,
)
from app.services.memory import memory_manager, ConversationTurn
from dotenv import load_dotenv

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
load_dotenv()

_START_TIME = time.perf_counter()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("sophia-backend")


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces API-key authentication on every non-public HTTP route."""

    def __init__(self, app: FastAPI, public_paths: Sequence[str]):
        super().__init__(app)
        self.public_paths = public_paths or []

    def _is_public(self, path: str) -> bool:
        """Return True when request path matches a configured public route."""
        for pattern in self.public_paths:
            if pattern == "*":
                return True
            if pattern.endswith("/*"):
                prefix = pattern[:-2]
                if path.startswith(prefix):
                    return True
            if path == pattern:
                return True
            # Allow prefix-style matches without needing explicit wildcard
            if (
                pattern
                and pattern != "/"
                and path.startswith(pattern.rstrip("/") + "/")
            ):
                return True
        return False

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        if request.method == "OPTIONS":
            return await call_next(request)
        if self._is_public(request.url.path):
            return await call_next(request)
        authorization = request.headers.get("Authorization")
        try:
            verify_api_key(request=request, authorization=authorization)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code, content={"detail": exc.detail}
            )
        return await call_next(request)


settings = get_settings()
validate_settings(settings)
<<<<<<< HEAD

app = FastAPI(title=settings.APP_NAME)

setup_tracer(app, settings)
supabase_service.init_supabase(settings)
=======
supabase_service.init_supabase(settings)

app = FastAPI(title=settings.APP_NAME)


def _looks_like_audio(payload: bytes) -> bool:
    """Lightweight magic-byte sniffing to catch obvious non-audio uploads."""
    if not payload or len(payload) < 4:
        return False
    head = payload[:4]
    if head == b"RIFF":  # WAV/WEBP containers
        return True
    if head[:3] == b"ID3":  # MP3 ID3 tag
        return True
    if head == b"OggS":
        return True
    if head == b"fLaC":
        return True
    # MPEG frame sync (11 set bits) catches many MP3/MP2 streams
    if payload[0] == 0xFF and (payload[1] & 0xE0) == 0xE0:
        return True
    # MP4/M4A files often start with an ftyp atom at offset 4
    if len(payload) >= 12 and payload[4:8] == b"ftyp":
        return True
    # As a last resort, treat files with enough non-zero bytes as plausible audio
    return any(b for b in payload[:512])


# ==========================
# Live Mode: WebSocket Voice
# ==========================


def _wav_header_pcm16(
    num_samples: int, sample_rate: int = 16000, num_channels: int = 1
) -> bytes:
    import struct

    byte_rate = sample_rate * num_channels * 2
    block_align = num_channels * 2
    data_size = num_samples * 2
    riff_chunk_size = 36 + data_size
    return b"".join(
        [
            b"RIFF",
            struct.pack("<I", riff_chunk_size),
            b"WAVE",
            b"fmt ",
            struct.pack(
                "<IHHIIHH", 16, 1, num_channels, sample_rate, byte_rate, block_align, 16
            ),
            b"data",
            struct.pack("<I", data_size),
        ]
    )


async def _ws_send_json(ws: WebSocket, obj: dict) -> None:
    import json as _json

    await ws.send_text(_json.dumps(obj))


def _avg_abs_pcm16(buf: bytes) -> float:
    if not buf:
        return 0.0
    import array

    a = array.array("h")
    a.frombytes(buf[: len(buf) - (len(buf) % 2)])
    if len(a) == 0:
        return 0.0
    s = sum(abs(x) for x in a)
    return s / len(a)


@app.websocket("/ws/voice")
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

    pcm_buffer = bytearray()
    last_voice_activity = time.time()
    in_speech = False
    utter_start_pos = 0
    last_final_text = ""
    last_reply_text = ""
    last_audio_url: Optional[str] = None

    session_id = str(uuid.uuid4())
    audio_queue = get_audio_queue_manager()
    manager = shared_services.get_session_turn_manager()
    metadata: Dict[str, Any] = {"endpoint": "/ws/voice"}
    if discord_id:
        metadata["discord_id"] = discord_id

    def _pcm16_to_wav(
        pcm_bytes: bytes, *, sample_rate: int = 48000, channels: int = 1
    ) -> bytes:
        """Wrap raw PCM16 bytes with a minimal WAV header so browsers can play each chunk."""
        import struct

        data_size = len(pcm_bytes)
        byte_rate = sample_rate * channels * 2
        block_align = channels * 2
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            36 + data_size,
            b"WAVE",
            b"fmt ",
            16,
            1,
            channels,
            sample_rate,
            byte_rate,
            block_align,
            16,
            b"data",
            data_size,
        )
        return header + pcm_bytes

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
                payload_bytes = _pcm16_to_wav(payload_bytes, sample_rate=sample_rate)
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

    try:
        while True:
            msg = await websocket.receive()
            if "bytes" in msg and msg["bytes"] is not None:
                chunk: bytes = msg["bytes"]
                if not chunk:
                    continue
                pcm_buffer.extend(chunk)

                now = time.time()
                recent = (
                    pcm_buffer[-SILENCE_BYTES:]
                    if len(pcm_buffer) > SILENCE_BYTES
                    else pcm_buffer
                )
                amp = _avg_abs_pcm16(recent)
                if amp > SILENCE_THRESHOLD:
                    if not in_speech:
                        in_speech = True
                        utter_start_pos = max(0, len(pcm_buffer) - len(recent))
                        barge_in_start = time.time()
                        active_turn = manager.get_active_turn(session_id)
                        interrupted_turn_id = (
                            active_turn.turn_id if active_turn else None
                        )
                        if interrupted_turn_id:
                            manager.request_cancel(turn_id=interrupted_turn_id)
                        current_cancelled, queue_cleared = audio_queue.cancel_all(
                            session_id
                        )
                        barge_in_ms = (time.time() - barge_in_start) * 1000
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
                        if barge_in_ms > 200:
                            logger.warning(
                                f"WS Session {session_id}: barge-in interruption took {barge_in_ms:.2f}ms (>200ms budget)"
                            )
                    last_voice_activity = now
                    continue

                if in_speech and (now - last_voice_activity) * 1000.0 >= SILENCE_MS:
                    utter_bytes = bytes(pcm_buffer[utter_start_pos:])
                    wav_utter = _wav_header_pcm16(len(utter_bytes) // 2) + utter_bytes
                    logger.info(
                        f"WS: endpoint detected; utterance bytes={len(utter_bytes)}"
                    )

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
                                # Check if this is tier-0 classification result
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

                        import re

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
                                for pcm_chunk in (
                                    synthesize_inworld_stream(
                                        sent, sample_rate_hz=48000
                                    )
                                    or []
                                ):
                                    cancel_check()
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
                                    audio_bytes = synthesize_inworld(sent)
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
                                    try:
                                        file_name = (
                                            f"sophia_{int(time.time() * 1000)}.mp3"
                                        )
                                        audio_url_last = (
                                            supabase_service.upload_audio_and_get_url(
                                                audio_bytes, file_name
                                            )
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
                                        logger.warning(
                                            "WS: failed uploading fallback sentence audio"
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
                                storage_audio = synthesize_inworld(
                                    reply_full,
                                    cancel_check=cancel_check,
                                )
                                file_name = f"sophia_{int(time.time() * 1000)}.mp3"
                                audio_url_last = (
                                    supabase_service.upload_audio_and_get_url(
                                        storage_audio, file_name
                                    )
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

                        last_final_text = f"[Audio processed: {len(utter_bytes)} bytes]"
                        last_reply_text = reply_full
                        last_audio_url = audio_url_last
                        turn_state.set_status("completed")

                    pcm_buffer.clear()
                    in_speech = False
                    last_voice_activity = now
            elif msg.get("type") == "websocket.disconnect":
                break
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


# OpenTelemetry setup
resource = Resource.create(
    {
        "service.name": "sophia-backend",
        "service.version": "1.0.0",
        "deployment.environment": "staging",
    }
)


def _normalize_otlp_endpoint(ep: Optional[str]) -> Optional[str]:
    if not ep:
        return None
    ep = ep.rstrip("/")
    # If caller passed base gateway (e.g., https://otlp-gateway.grafana.net/otlp),
    # add the traces path expected by the HTTP exporter.
    if not ep.endswith("/v1/traces"):
        # Common Grafana endpoints end in "/otlp". Either way, append the traces path cleanly.
        return f"{ep}/v1/traces"
    return ep


def _parse_otlp_headers(hdrs: Optional[str]) -> Optional[dict[str, str]]:
    if not hdrs:
        return None
    # Support comma-separated key=value pairs, e.g. "Authorization=Bearer abc, X-Org=123"
    out: dict[str, str] = {}
    for part in hdrs.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out or None


provider = TracerProvider(resource=resource)
otlp_endpoint = _normalize_otlp_endpoint(settings.OTEL_EXPORTER_OTLP_ENDPOINT)
otlp_headers = _parse_otlp_headers(settings.OTEL_EXPORTER_OTLP_HEADERS)
if otlp_endpoint:
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, headers=otlp_headers)
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("sophia")
FastAPIInstrumentor.instrument_app(app)
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)

app.add_middleware(APIKeyMiddleware, public_paths=settings.API_PUBLIC_PATHS)

allowed_cors_origins = settings.CORS_ALLOWED_ORIGINS or ["http://localhost:3000"]
logger.info("Configuring CORS for allowed origins: %s", allowed_cors_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
        "X-Api-Key",
    ],
    expose_headers=["Authorization"],
    max_age=86400,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount static files for frontend (only if frontend directory exists)
# In backend-only deployment (Render), frontend is served separately by Vercel
<<<<<<< HEAD
=======

>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
if os.path.exists("frontend"):
    app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
    logger.info("Frontend static files mounted at /frontend")
else:
    logger.info(
        "Frontend directory not found - running in backend-only mode (frontend served by Vercel)"
    )

<<<<<<< HEAD
app.include_router(admin_router.router)
app.include_router(chat_router.router)
app.include_router(evaluation_router.router)

=======
logger.info(
    "Startup initialization completed in %.2f s", time.perf_counter() - _START_TIME
)
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)

# Simple health endpoint for Fly.io checks and container orchestration
@app.get("/health")
def health():
<<<<<<< HEAD
    """Basic liveness endpoint."""
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint for monitoring.

    Exposes metrics including:
    - memo_write_success_rate: Memory write success rate (%)
    - memo_writes_total: Total memory write attempts (by status)
    - memo_searches_total: Total memory search attempts (by status)
    - memo_search_latency_seconds: Memory search latency (avg, p95)
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
=======
    return {"status": "ok"}


class Emotion(BaseModel):
    label: str
    confidence: float


class TranscriptionResponse(BaseModel):
    text: str
    emotion: Emotion


class GenerateResponse(BaseModel):
    reply: str
    tone: Optional[str] = "neutral"


class SynthesizeResponse(BaseModel):
    audio_url: str
    emotion: Emotion


class ChatResponse(BaseModel):
    transcript: str
    reply: str
    user_emotion: Emotion
    sophia_emotion: Emotion
    audio_url: str
    intent: Optional[str] = None
    context_memory: Optional[dict] = None
    evaluation_report: Optional[dict] = None


class DefiChatResponse(BaseModel):
    session_id: str
    transcript: str
    reply: str
    response_path: Optional[str] = None
    user_emotion: Emotion
    sophia_emotion: Emotion
    audio_url: str
    intent: str
    context_memory: dict
    fallbacks_used: dict
    evaluation_logs: list
    evaluation_report: Optional[dict] = None


class TextChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)


@app.get("/")
def root(request: Request):
    """Backend status with optional static frontend response."""
    accepts = request.headers.get("accept", "")
    if "text/html" in accepts.lower() and os.path.exists("frontend/index.html"):
        # Full-stack deployment: serve frontend to browser clients requesting HTML
        return FileResponse("frontend/index.html")

    # Backend-only deployment: return API info (default for API clients/tests)
    return {
        "message": "Sophia AI Backend is running",
        "frontend_url": "https://sophia-1st-mvp-git-main-davidelavergas-projects.vercel.app",
        "api_status": "ok",
        "deployment_mode": "backend+api"
        if os.path.exists("frontend/index.html")
        else "backend-only",
        "docs_url": "/docs",
    }

<<<<<<< HEAD

logger.info(
    "Startup initialization completed in %.2f s", time.perf_counter() - _START_TIME
)
=======
@app.get("/api")
def api_root():
    """API status endpoint"""
    return {"message": "Sophia AI Backend with DeFi Agent is running."}


@app.post("/transcribe", response_model=TranscriptionResponse)
@limiter.limit(settings.API_RATE_LIMIT)
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    supabase_token: str = Depends(verify_api_key),
):
    # Accept common audio formats (extension and content type)
    allowed_extensions = [
        '.wav',
        '.webm',
        '.mp4',
        '.ogg',
        '.flac',
        '.m4a',
        '.aac',
    ]
    allowed_content_types = {
        'audio/wav',
        'audio/x-wav',
        'audio/webm',
        'audio/ogg',
        'audio/flac',
        'audio/mp4',
        'audio/aac',
    }
    filename = (file.filename or '').lower()
    content_type = (file.content_type or '').lower()
    if not any(filename.endswith(ext) for ext in allowed_extensions) or content_type not in allowed_content_types:
        raise HTTPException(
            status_code=400,
            detail=(
                "File must be a supported audio format."
                " Supported formats: wav, webm, mp4, ogg, flac, m4a, aac"
            ),
        )

    session_id = uuid.uuid4()

    try:
        wav_bytes = await file.read()
        if not _looks_like_audio(wav_bytes):
            raise HTTPException(
                status_code=400, detail="File must contain recognizable audio data"
            )
        text = mistral_service.transcribe_audio_with_voxtral(wav_bytes)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=500, detail="Transcription failed")

    user_emotion = analyze_emotion_audio(wav_bytes)
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


class GenerateRequest(BaseModel):
    text: str


@app.post("/generate-response", response_model=GenerateResponse)
@limiter.limit(settings.API_RATE_LIMIT)
async def generate_response(
    request: Request,
    body: GenerateRequest,
    supabase_token: str = Depends(verify_api_key),
):
    try:
        reply = mistral_service.generate_llm_reply(body.text)
    except Exception:
        logger.exception("LLM response generation failed")
        raise HTTPException(status_code=500, detail="Response generation failed")

    return GenerateResponse(reply=reply, tone="encouraging")


@app.post("/generate-response/stream")
@limiter.limit(settings.API_RATE_LIMIT)
async def generate_response_stream(
    request: Request,
    body: GenerateRequest,
    supabase_token: str = Depends(verify_api_key),
):
    """Stream LLM tokens as they are generated.

    Returns plain text chunks; the client should append them to display the
    streaming answer. This endpoint is ideal for chat UIs that want low-latency
    first token and incremental updates.
    """
    try:
        generator = mistral_service.stream_generate_llm_reply(body.text)
        return StreamingResponse(generator, media_type="text/plain")
    except Exception:
        logger.exception("Streaming response generation failed")
        raise HTTPException(
            status_code=500, detail="Streaming response generation failed"
        )


class SynthesizeRequest(BaseModel):
    text: str


@app.post("/synthesize", response_model=SynthesizeResponse)
@limiter.limit(settings.API_RATE_LIMIT)
async def synthesize(
    request: Request,
    body: SynthesizeRequest,
    supabase_token: str = Depends(verify_api_key),
):
    supabase_user_id, _ = extract_identity_from_token(supabase_token)
    try:
        audio_bytes = synthesize_inworld(body.text)
    except Exception:
        logger.exception("TTS synthesis failed")
        raise HTTPException(status_code=500, detail="Synthesis failed")

    try:
        file_name = f"sophia_{int(time.time() * 1000)}.mp3"
        # Fix argument order: first bytes, then optional file_name
        audio_url = supabase_service.upload_audio_and_get_url(audio_bytes, file_name)
    except Exception:
        logger.exception("Audio upload failed")
        raise HTTPException(status_code=500, detail="Audio upload failed")

    sophia_emotion = analyze_emotion_audio(audio_bytes)

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


@app.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.API_RATE_LIMIT)
async def chat(
    request: Request,
    file: UploadFile = File(...),
    supabase_token: str = Depends(verify_api_key),
    consent_ok: None = Depends(require_consent),
):
    supabase_user_id, discord_id = extract_identity_from_token(supabase_token)
    manager = shared_services.get_session_turn_manager()
    # Accept common audio formats (extension and content type)
    allowed_extensions = [
        '.wav',
        '.webm',
        '.mp4',
        '.ogg',
        '.flac',
        '.m4a',
        '.aac',
    ]
    allowed_content_types = {
        'audio/wav',
        'audio/x-wav',
        'audio/webm',
        'audio/ogg',
        'audio/flac',
        'audio/mp4',
        'audio/aac',
    }
    filename = (file.filename or '').lower()
    content_type = (file.content_type or '').lower()
    if not any(filename.endswith(ext) for ext in allowed_extensions) or content_type not in allowed_content_types:
        raise HTTPException(
            status_code=400,
            detail=(
                "File must be a supported audio format."
                " Supported formats: wav, webm, mp4, ogg, flac, m4a, aac"
            ),
        )

    session_uuid = uuid.uuid4()
    session_id_str = str(session_uuid)
    metadata: Dict[str, Any] = {"endpoint": "/chat"}
    if discord_id:
        metadata["discord_id"] = discord_id

    async with manage_session_turn(session_id_str, metadata=metadata) as turn_state:

        def cancel_check():
            manager.raise_if_cancelled(turn_state.turn_id)

        with tracer.start_as_current_span("chat") as chat_span:
            chat_span.set_attribute("session.id", session_id_str)
            t0 = time.time()
            try:
                wav_bytes = await file.read()
                with tracer.start_as_current_span("stt_transcription") as stt_span:
                    transcript = mistral_service.transcribe_audio_with_voxtral(
                        wav_bytes,
                        cancel_check=cancel_check,
                    )
                    stt_span.set_attribute("transcript.length", len(transcript))
            except Exception:
                logger.exception("Transcription failed in chat")
                raise HTTPException(status_code=500, detail="Transcription failed")

            cancel_check()

            with tracer.start_as_current_span("emotion_analysis_user") as emotion_span:
                user_emotion = analyze_emotion_audio(wav_bytes)
                emotion_span.set_attribute(
                    "phoenix_user_emotion.label", user_emotion.label
                )
                emotion_span.set_attribute(
                    "phoenix_user_emotion.confidence", float(user_emotion.confidence)
                )
                emotion_span.set_attribute("emotion.type", "user")
                emotion_span.set_attribute("emotion.source", "audio")

            chat_span.set_attribute("phoenix_user_emotion.label", user_emotion.label)
            chat_span.set_attribute(
                "phoenix_user_emotion.confidence", float(user_emotion.confidence)
            )

            try:
                turn_state.set_status("streaming")
                cancel_check()
                with tracer.start_as_current_span("llm_generation") as llm_span:
                    reply = mistral_service.generate_llm_reply(
                        transcript,
                        cancel_check=cancel_check,
                    )
                    llm_span.set_attribute("reply.length", len(reply))
            except Exception:
                logger.exception("LLM generation failed in chat")
                raise HTTPException(
                    status_code=500, detail="Response generation failed"
                )

            try:
                turn_state.set_status("synthesizing")
                cancel_check()
                with tracer.start_as_current_span("tts_synthesis_upload"):
                    audio_bytes = synthesize_inworld(
                        reply,
                        cancel_check=cancel_check,
                    )
                    file_name = f"sophia_{int(time.time() * 1000)}.mp3"
                    audio_url = supabase_service.upload_audio_and_get_url(
                        audio_bytes, file_name
                    )
            except Exception:
                logger.exception("Synthesis or upload failed in chat")
                raise HTTPException(status_code=500, detail="Synthesis failed")

            with tracer.start_as_current_span(
                "emotion_analysis_sophia"
            ) as sophia_emotion_span:
                sophia_emotion = analyze_emotion_audio(audio_bytes)
                sophia_emotion_span.set_attribute(
                    "phoenix_sophia_emotion.label", sophia_emotion.label
                )
                sophia_emotion_span.set_attribute(
                    "phoenix_sophia_emotion.confidence",
                    float(sophia_emotion.confidence),
                )
                sophia_emotion_span.set_attribute("emotion.type", "sophia")
                sophia_emotion_span.set_attribute("emotion.source", "audio")

            chat_span.set_attribute(
                "phoenix_sophia_emotion.label", sophia_emotion.label
            )
            chat_span.set_attribute(
                "phoenix_sophia_emotion.confidence", float(sophia_emotion.confidence)
            )

            total_ms = int((time.time() - t0) * 1000)
            chat_span.set_attribute("total_roundtrip_time.ms", total_ms)

        try:
            supabase_service.insert_conversation_session(
                {
                    "id": session_id_str,
                    "transcript": transcript,
                    "reply": reply,
                    "user_emotion_label": user_emotion.label,
                    "user_emotion_confidence": user_emotion.confidence,
                    "sophia_emotion_label": sophia_emotion.label,
                    "sophia_emotion_confidence": sophia_emotion.confidence,
                    "audio_url": audio_url or None,
                    "user_id": supabase_user_id,
                },
                access_token=supabase_token,
            )
            try:
                supabase_service.insert_emotion_score(
                    session_uuid,
                    role="user",
                    emotion=user_emotion,
                    user_id=supabase_user_id,
                    access_token=supabase_token,
                )
            except Exception:
                logger.warning("Persist user emotion failed; continuing")
            try:
                supabase_service.insert_emotion_score(
                    session_uuid,
                    role="sophia",
                    emotion=sophia_emotion,
                    user_id=supabase_user_id,
                    access_token=supabase_token,
                )
            except Exception:
                logger.warning("Persist sophia emotion failed; continuing")
        except Exception:
            logger.warning("Persist conversation session failed; continuing")

        turn_state.set_status("completed")
        return ChatResponse(
            transcript=transcript,
            reply=reply,
            user_emotion=user_emotion.model_dump(),
            sophia_emotion=sophia_emotion.model_dump(),
            audio_url=audio_url,
        )


@app.post("/defi-chat", response_model=DefiChatResponse)
@limiter.limit(settings.API_RATE_LIMIT)
async def defi_chat(
    request: Request,
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
    supabase_token: str = Depends(verify_api_key),
    consent_ok: None = Depends(require_consent),
):
    user_id, discord_id = extract_identity_from_token(supabase_token)
    allowed_extensions = [
        ".wav",
        ".webm",
        ".mp3",
        ".mp4",
        ".ogg",
        ".flac",
        ".m4a",
        ".aac",
    ]
    if not any(file.filename.lower().endswith(ext) for ext in allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail=f"File must be an audio file. Supported formats: {', '.join(allowed_extensions)}",
        )

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
            wav_bytes = await file.read()
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
            try:
                supabase_service.insert_conversation_session(
                    {
                        "id": result["session_id"],
                        "transcript": result["transcript"],
                        "reply": result["reply"],
                        "user_emotion_label": result["user_emotion"]["label"],
                        "user_emotion_confidence": result["user_emotion"]["confidence"],
                        "sophia_emotion_label": result["sophia_emotion"]["label"],
                        "sophia_emotion_confidence": result["sophia_emotion"][
                            "confidence"
                        ],
                        "audio_url": result["audio_url"] or None,
                        "intent": result["intent"],
                        "context_memory": str(result["context_memory"]),
                        "user_id": user_id,
                    },
                    access_token=supabase_token,
                )
                try:
                    cancel_check()
                    supabase_service.insert_emotion_score(
                        result["session_id"],
                        role="user",
                        emotion=type("E", (), result["user_emotion"])(),
                        user_id=user_id,
                        access_token=supabase_token,
                    )
                except Exception as e:
                    logger.warning(f"Failed to persist user emotion: {e}")
                try:
                    cancel_check()
                    supabase_service.insert_emotion_score(
                        result["session_id"],
                        role="sophia",
                        emotion=type("E", (), result["sophia_emotion"])(),
                        user_id=user_id,
                        access_token=supabase_token,
                    )
                except Exception as e:
                    logger.warning(f"Failed to persist sophia emotion: {e}")
            except Exception as e:
                logger.warning(f"Failed to persist conversation session: {e}")

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


@app.post("/defi-chat/stream")
@limiter.limit(settings.API_RATE_LIMIT)
async def defi_chat_stream(
    request: Request,
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
    supabase_token: str = Depends(verify_api_key),
    consent_ok: None = Depends(require_consent),
):
    """Streaming variant of DeFi chat.

    Server-Sent Events (SSE) stream with events:
    - event: transcript, data: { transcript, user_emotion }
    - event: token, data: <text chunk>
    - event: reply_done, data: { reply }
    - event: audio_url, data: { audio_url, sophia_emotion }
    """
    user_id, discord_id = extract_identity_from_token(supabase_token)
    session_identifier = session_id or str(uuid.uuid4())
    metadata: Dict[str, Any] = {"endpoint": "/defi-chat/stream"}
    if session_id:
        metadata["provided_session_id"] = session_id
    if discord_id:
        metadata["discord_id"] = discord_id
    manager = shared_services.get_session_turn_manager()
    # IMPORTANT: Read the uploaded file BEFORE starting the generator.
    # Starlette may close the underlying SpooledTemporaryFile once the coroutine
    # returns control, which would make subsequent reads fail within the
    # generator with "I/O operation on closed file".
    wav_bytes = await file.read()

    async def event_generator():
        nonlocal session_id
        async with manage_session_turn(
            session_identifier, metadata=metadata
        ) as turn_state:
            session_id_local = session_identifier
            session_id = session_id_local

            def cancel_check():
                manager.raise_if_cancelled(turn_state.turn_id)

            try:
                cancel_check()
                transcript = mistral_service.transcribe_audio_with_voxtral(
                    wav_bytes,
                    cancel_check=cancel_check,
                )
                cancel_check()
                user_emotion = analyze_emotion_audio(wav_bytes)

                import json as _json

                yield f"event: transcript\ndata: {_json.dumps({'transcript': transcript, 'user_emotion': user_emotion.model_dump(), 'session_id': session_id_local})}\n\n"

                turn_state.set_status("streaming")
                reply_accum = []
                for chunk in mistral_service.stream_generate_llm_reply(
                    transcript,
                    cancel_check=cancel_check,
                ):
                    cancel_check()
                    if not chunk:
                        continue
                    reply_accum.append(chunk)
                    safe_chunk = chunk.replace("\n", " ")
                    yield f"event: token\ndata: {safe_chunk}\n\n"

                reply = "".join(reply_accum).strip()
                yield f"event: reply_done\ndata: {_json.dumps({'reply': reply})}\n\n"

                turn_state.set_status("synthesizing")
                cancel_check()
                try:
                    audio_bytes = synthesize_inworld(
                        reply,
                        cancel_check=cancel_check,
                    )
                    cancel_check()
                    file_name = f"sophia_{int(time.time() * 1000)}.mp3"
                    audio_url = supabase_service.upload_audio_and_get_url(
                        audio_bytes, file_name
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Synthesis or upload failed in defi_chat_stream")
                    audio_url = None

                sophia_emotion = None
                mock_audio = False
                try:
                    if audio_url:
                        try:
                            mock_audio = (
                                audio_bytes.startswith(b"ID3mock")
                                or len(audio_bytes) < 2048
                            )
                        except Exception:
                            mock_audio = False
                        cancel_check()
                        sophia_emotion = analyze_emotion_audio(audio_bytes)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning("Sophia emotion analysis failed; continuing")

                try:
                    cancel_check()
                    supabase_service.insert_conversation_session(
                        {
                            "id": session_id_local,
                            "transcript": transcript,
                            "reply": reply,
                            "user_emotion_label": user_emotion.label,
                            "user_emotion_confidence": user_emotion.confidence,
                            "sophia_emotion_label": (
                                sophia_emotion.label if sophia_emotion else None
                            ),
                            "sophia_emotion_confidence": (
                                sophia_emotion.confidence if sophia_emotion else None
                            ),
                            "audio_url": audio_url or None,
                            "user_id": user_id,
                        },
                        access_token=supabase_token,
                    )
                    try:
                        cancel_check()
                        supabase_service.insert_emotion_score(
                            session_id_local,
                            role="user",
                            emotion=user_emotion,
                            user_id=user_id,
                            access_token=supabase_token,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to persist user emotion: {e}")
                    try:
                        if sophia_emotion:
                            cancel_check()
                            supabase_service.insert_emotion_score(
                                session_id_local,
                                role="sophia",
                                emotion=sophia_emotion,
                                user_id=user_id,
                                access_token=supabase_token,
                            )
                    except Exception as e:
                        logger.warning(f"Failed to persist sophia emotion: {e}")
                except Exception as e:
                    logger.warning(
                        f"Failed to persist conversation session (stream): {e}"
                    )

                turn_state.set_status("completed")

                payload = {
                    "audio_url": audio_url,
                    "sophia_emotion": (
                        sophia_emotion.model_dump() if sophia_emotion else None
                    ),
                    "mock_audio": mock_audio,
                }
                yield f"event: audio_url\ndata: {_json.dumps(payload)}\n\n"

            except asyncio.CancelledError:
                logger.info("Streaming DeFi chat turn %s cancelled", turn_state.turn_id)
                raise
            except Exception as e:
                logger.exception("Streaming DeFi chat failed")
                import json as _json

                error_payload = _json.dumps({"detail": str(e)})
                yield f"event: error\ndata: {error_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# ==========================
# Live Mode: WebSocket Voice
# ==========================

def _wav_header_pcm16(num_samples: int, sample_rate: int = 16000, num_channels: int = 1) -> bytes:
    import struct
    byte_rate = sample_rate * num_channels * 2
    block_align = num_channels * 2
    data_size = num_samples * 2
    riff_chunk_size = 36 + data_size
    return b"".join([
        b"RIFF",
        struct.pack("<I", riff_chunk_size),
        b"WAVE",
        b"fmt ",
        struct.pack("<IHHIIHH", 16, 1, num_channels, sample_rate, byte_rate, block_align, 16),
        b"data",
        struct.pack("<I", data_size),
    ])

async def _ws_send_json(ws: WebSocket, obj: dict):
    import json as _json
    await ws.send_text(_json.dumps(obj))

def _avg_abs_pcm16(buf: bytes) -> float:
    if not buf:
        return 0.0
    import array
    a = array.array('h')
    a.frombytes(buf[: len(buf) - (len(buf) % 2)])
    if len(a) == 0:
        return 0.0
    s = sum(abs(x) for x in a)
    return s / len(a)

@app.websocket("/ws/voice_old")
async def ws_voice_old(websocket: WebSocket):
    # In production, protect with auth (API key/session) via headers or query.
    await websocket.accept()
    session_id = str(uuid.uuid4())
    log_prefix = f"[ws_voice:{session_id}]"
    logger.info(f"{log_prefix} connection accepted")
    SAMPLE_RATE = 16000
    BYTES_PER_SEC = SAMPLE_RATE * 2  # pcm16 mono
    CHUNK_MS = 200
    SILENCE_THRESHOLD = 300  # avg abs amplitude heuristic (lower => more responsive)
    SILENCE_MS = 600  # shorter endpointing delay for faster replies
    SILENCE_BYTES = int(BYTES_PER_SEC * (SILENCE_MS / 1000.0))

    pcm_buffer = bytearray()
    partial_transcript = ""
    last_partial_emit = 0.0
    last_voice_activity = time.time()
    in_speech = False
    utter_start_pos = 0
    # Live-mode summary state for end-of-call persistence
    last_final_text = ""
    last_reply_text = ""
    last_audio_url: Optional[str] = None

    first_chunk_logged = False
    turn_index = 0

    try:
        while True:
            msg = await websocket.receive()
            if "bytes" in msg and msg["bytes"] is not None:
                chunk: bytes = msg["bytes"]
                if not chunk:
                    continue
                pcm_buffer.extend(chunk)
                if not first_chunk_logged:
                    logger.debug(f"{log_prefix} first audio chunk received len={len(chunk)}")
                    first_chunk_logged = True

                # Skip partial transcripts for faster experience - go directly to Voxtral
                # User doesn't need to see transcription, just fast response

                # Simple amplitude-based VAD
                now = time.time()
                recent = pcm_buffer[-SILENCE_BYTES:] if len(pcm_buffer) > SILENCE_BYTES else pcm_buffer
                amp = _avg_abs_pcm16(recent)
                if amp > SILENCE_THRESHOLD:
                    if not in_speech:
                        in_speech = True
                        utter_start_pos = max(0, len(pcm_buffer) - len(recent))
                        logger.info(f"{log_prefix} speech started at {utter_start_pos} bytes (amp={amp:.1f})")
                    last_voice_activity = now

                # Endpoint: long enough silence after speech - no transcription needed
                if in_speech and (now - last_voice_activity) * 1000.0 >= SILENCE_MS:
                    # Extract utterance audio segment for direct Voxtral processing
                    utter_bytes = bytes(pcm_buffer[utter_start_pos:])
                    wav_utter = _wav_header_pcm16(len(utter_bytes) // 2) + utter_bytes
                    logger.info(f"{log_prefix} endpoint detected; utterance bytes={len(utter_bytes)}")

                    # Process audio through LangGraph pipeline (non-streaming for reliability)
                    reply_tokens = []
                    tokens_sent = 0
                    turn_index += 1
                    logger.debug(f"{log_prefix} turn {turn_index} processing via LangGraph")
                    try:
                        result = langgraph_service.process_conversation(
                            audio_bytes=wav_utter,
                            session_id=session_id,
                            collect_evaluation_data=True,
                        )
                        # Align local session identifier with whatever LangGraph persisted
                        langgraph_session_id = result.get("session_id")
                        if langgraph_session_id and langgraph_session_id != session_id:
                            logger.debug(
                                f"{log_prefix} adopting LangGraph session_id {langgraph_session_id}"
                            )
                            session_id = langgraph_session_id
                            log_prefix = f"[ws_voice:{session_id}]"
                        reply_full = (result.get("reply") or "").strip()
                        if not reply_full:
                            reply_full = "I'm having trouble processing that. Could you try again?"
                        logger.debug(f"{log_prefix} turn {turn_index} LangGraph reply received len={len(reply_full)}")
                        # Simulate streaming by chunking
                        chunk_size = 12
                        for i in range(0, len(reply_full), chunk_size):
                            chunk = reply_full[i:i+chunk_size]
                            reply_tokens.append(chunk)
                            await _ws_send_json(websocket, {"type": "token", "text": chunk})
                            tokens_sent += 1
                        logger.info(f"{log_prefix} LangGraph processed successfully, reply_len={len(reply_full)}")
                    except Exception as e:
                        logger.exception(f"{log_prefix} LangGraph processing failed: {e}")
                        reply_full = "I'm having trouble right now. Please try again."
                        await _ws_send_json(websocket, {"type": "token", "text": reply_full})
                        reply_tokens.append(reply_full)
                        tokens_sent += 1

                    # Final fallback: synthetic chunking
                    if tokens_sent == 0:
                        try:
                            logger.info(f"{log_prefix} no tokens streamed; using minimal fallback")
                            full = "Okay."
                        except Exception as e:
                            logger.warning(f"{log_prefix} generate_llm_reply fallback failed: {e}")
                            full = "Okay."
                        chunk_size = 16
                        for i in range(0, len(full), chunk_size):
                            await _ws_send_json(websocket, {"type": "token", "text": full[i:i+chunk_size]})
                            tokens_sent += 1
                        reply_full = full.strip() or "Okay."
                    else:
                        reply_full = "".join(reply_tokens).strip() or "Okay."
                    logger.debug(f"{log_prefix} turn {turn_index} tokens streamed={tokens_sent}")
                    logger.info(f"{log_prefix} token streaming complete; tokens_sent={tokens_sent}, reply_len={len(reply_full)}")
                    await _ws_send_json(websocket, {"type": "reply_done", "text": reply_full})
                    logger.debug(f"{log_prefix} turn {turn_index} reply_done event sent")

                    # Streaming TTS: split reply into short sentences; for each sentence synthesize once
                    # and emit base64 audio chunks immediately. Also keep URL events for backward compat.
                    import re
                    sentences = [s.strip() for s in re.split(r"(?<=[\.!?])\s+", reply_full) if s.strip()]
                    audio_url_last = None
                    for i, sent in enumerate(sentences):
                        try:
                            logger.debug(f"{log_prefix} TTS streaming sentence {i+1}/{len(sentences)} len={len(sent)}")
                            import base64 as _b64
                            streamed_any = False
                            try:
                                # Stream each sentence as individual audio chunks
                                for pcm_chunk in synthesize_inworld_stream(sent, sample_rate_hz=48000) or []:
                                    streamed_any = True
                                    b64 = _b64.b64encode(pcm_chunk).decode('ascii')
                                    # audio/wav because first chunk includes WAV header, subsequent are PCM
                                    await _ws_send_json(websocket, {"type": "audio_chunk", "mime": "audio/wav", "b64": b64, "eos": False})
                                    logger.debug(f"{log_prefix} streamed audio chunk sentence={i+1}")
                            except Exception:
                                logger.exception(f"{log_prefix} inworld streaming failed; falling back to non-streaming TTS for this sentence")

                            if not streamed_any:
                                # Fallback: synthesize whole sentence as complete audio
                                try:
                                    audio_bytes = synthesize_inworld(sent)
                                    mock_check = str(audio_bytes).startswith("b'ID3mock")
                                    logger.info(f"{log_prefix} fallback TTS bytes={len(audio_bytes)} (mock={mock_check})")

                                    # Send complete sentence audio as single chunk for immediate playback
                                    b64 = _b64.b64encode(audio_bytes).decode('ascii')
                                    await _ws_send_json(websocket, {"type": "audio_chunk", "mime": "audio/mpeg", "b64": b64, "eos": False})

                                    # Also upload the full sentence MP3 to storage (optional/back-compat)
                                    try:
                                        file_name = f"sophia_{int(time.time()*1000)}.mp3"
                                        audio_url_chunk = supabase_service.upload_audio_and_get_url(audio_bytes, file_name)
                                        audio_url_last = audio_url_chunk
                                        logger.info(f"{log_prefix} uploaded audio chunk -> {audio_url_chunk}")
                                        await _ws_send_json(websocket, {"type": "audio_url_chunk", "audio_url": audio_url_chunk})
                                    except Exception:
                                        logger.warning(f"{log_prefix} upload of TTS sentence failed; continuing with streamed chunks only")
                                except Exception as e:
                                    logger.error(f"{log_prefix} fallback TTS synthesis failed for sentence: {e}")
                        except Exception:
                            logger.exception(f"{log_prefix} TTS or upload chunk failed")
                            continue

                    # Signal end-of-stream for this reply's audio
                    await _ws_send_json(websocket, {"type": "audio_chunk", "mime": "audio/wav", "b64": "", "eos": True})
                    logger.debug(f"{log_prefix} turn {turn_index} audio eos sent")
                    # Also send final audio_url for compatibility
                    await _ws_send_json(websocket, {"type": "audio_url", "audio_url": audio_url_last})
                    logger.debug(f"{log_prefix} turn {turn_index} final audio_url event sent {audio_url_last}")

                    # Update summary for end-of-call persistence
                    # Note: WebSocket uses direct audio processing, no explicit transcript
                    last_final_text = f"[Audio processed: {len(utter_bytes)} bytes]"
                    last_reply_text = reply_full
                    last_audio_url = audio_url_last

                    # Reset for next utterance
                    partial_transcript = ""
                    in_speech = False
                    last_partial_emit = now
                    last_voice_activity = now
            elif msg.get("type") == "websocket.disconnect":
                logger.info(f"{log_prefix} disconnect frame received from client")
                break
    except WebSocketDisconnect as exc:
        logger.info(f"{log_prefix} client disconnected code={getattr(exc, 'code', None)} reason={getattr(exc, 'reason', None)}")
    except Exception as e:
        logger.exception(f"{log_prefix} unexpected error: {e}")
        await _ws_send_json(websocket, {"type": "error", "detail": str(e)})
        try:
            await websocket.close()
        except Exception:
            logger.debug(f"{log_prefix} websocket close during error handling failed")
    finally:
        logger.info(f"{log_prefix} closing session")
        # Persist a single conversation summary at hangup (best-effort, no emotions to keep it fast)
        try:
            if last_final_text or last_reply_text:
                supabase_service.insert_conversation_session({
                    "id": session_id,
                    "transcript": last_final_text,
                    "reply": last_reply_text,
                    "audio_url": last_audio_url or None,
                })
                logger.debug(f"{log_prefix} persisted conversation summary")
        except Exception as persist_exc:
            logger.warning(f"{log_prefix} failed to persist conversation summary: {persist_exc}")


@app.post("/text-chat", response_model=DefiChatResponse)
@limiter.limit(settings.API_RATE_LIMIT)
async def text_chat(
    request: Request,
    body: TextChatRequest,
    supabase_token: str = Depends(verify_api_key),
    consent_ok: None = Depends(require_consent),
):
    """Text-only chat endpoint for DeFi conversations"""
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
            try:
                supabase_service.insert_conversation_session(
                    {
                        "id": result["session_id"],
                        "transcript": result["transcript"],
                        "reply": result["reply"],
                        "audio_url": result.get("audio_url") or None,
                        "intent": result.get("intent"),
                        "context_memory": str(result.get("context_memory")),
                        "user_id": user_id,
                    },
                    access_token=supabase_token,
                )
                try:
                    cancel_check()
                    supabase_service.insert_emotion_score(
                        result["session_id"],
                        role="user",
                        emotion=type("E", (), result["user_emotion"])(),
                        user_id=user_id,
                        access_token=supabase_token,
                    )
                except Exception as e:
                    logger.warning(f"Failed to persist user emotion: {e}")
                try:
                    cancel_check()
                    supabase_service.insert_emotion_score(
                        result["session_id"],
                        role="sophia",
                        emotion=type("E", (), result["sophia_emotion"])(),
                        user_id=user_id,
                        access_token=supabase_token,
                    )
                except Exception as e:
                    logger.warning(f"Failed to persist sophia emotion: {e}")
            except Exception as e:
                logger.warning(f"Failed to persist text conversation session: {e}")

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


def _format_memory_context_for_prompt(context: Optional[Dict[str, Any]]) -> str:
    if not context:
        return ""

    parts: list[str] = []
    topics = context.get("last_topics") or []
    if topics:
        parts.append(f"Recent topics: {', '.join(topics)}")

    tone = context.get("last_user_tone")
    if tone:
        parts.append(f"Previous user tone: {tone}")

    intents = context.get("recent_intents") or []
    if intents:
        parts.append(f"Recent intents: {', '.join(intents)}")

    recent_turns = context.get("recent_turns") or []
    if recent_turns:
        snippet_lines: list[str] = [
            "Conversation so far (use for context only; do not repeat lines verbatim):"
        ]
        for turn in recent_turns[-3:]:
            user_line = (turn.get("user") or "").strip()
            sophia_line = (turn.get("sophia") or "").strip()
            if user_line:
                snippet_lines.append(f"User: {user_line}")
            if sophia_line:
                snippet_lines.append(f"Sophia: {sophia_line}")
        if len(snippet_lines) > 1:
            parts.append("\n".join(snippet_lines))

    return "\n".join(parts)


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


@app.post("/text-chat/stream")
@limiter.limit(settings.API_RATE_LIMIT)
async def text_chat_stream(
    request: Request,
    body: TextChatRequest,
    supabase_token: str = Depends(verify_api_key),
    consent_ok: None = Depends(require_consent),
):
    """Streaming variant for text-only chat.

    Server-Sent Events (SSE) with:
    - event: token, data: <text chunk>
    - event: reply_done, data: { reply }
    - event: audio_url, data: { audio_url, sophia_emotion }
    """
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
                import json as _json

                emotion_label = "neutral"
                emotion_conf = 0.7
                user_emotion_payload: Dict[str, Any] = {
                    "label": emotion_label,
                    "confidence": emotion_conf,
                }

                try:
                    user_emotion = infer_text_emotion(body.message)
                    user_emotion_payload = user_emotion.model_dump()
                    emotion_label = user_emotion.label
                    emotion_conf = float(user_emotion.confidence)
                except Exception as emotion_error:
                    logger.warning(
                        "Text chat stream emotion detection failed: %s", emotion_error
                    )

                emotion_guidance: Sequence[str] = []

                try:
                    emotion_guidance = get_emotional_guidance(emotion_label)
                    if emotion_guidance:
                        preview = "; ".join(emotion_guidance[:2])
                        logger.info(
                            "Text chat stream guidance for %s: %s%s",
                            emotion_label,
                            preview,
                            "..." if len(emotion_guidance) > 2 else "",
                        )
                except Exception as guidance_error:
                    logger.warning(
                        "Text chat stream guidance lookup failed: %s", guidance_error
                    )
                    emotion_guidance = []

                memory_context_text = ""
                try:
                    flash_context = memory_manager.get_context_for_llm(
                        session_identifier, access_token=supabase_token
                    )
                    memory_context_text = _format_memory_context_for_prompt(
                        flash_context
                    )
                except Exception as context_error:
                    logger.warning(
                        "Text chat stream memory lookup failed: %s", context_error
                    )
                    memory_context_text = ""

                guided_prompt = build_emotion_guided_prompt(
                    body.message,
                    emotion_label,
                    emotion_conf,
                    emotion_guidance,
                    conversation_context=memory_context_text,
                )

                turn_state.set_status("streaming")
                reply_accum = []
                for chunk in mistral_service.stream_generate_llm_reply(
                    guided_prompt,
                    cancel_check=cancel_check,
                ):
                    cancel_check()
                    if not chunk:
                        continue
                    reply_accum.append(chunk)
                    safe_chunk = chunk.replace("\n", " ")
                    yield f"event: token\ndata: {safe_chunk}\n\n"

                reply = "".join(reply_accum).strip()
                reply_payload = {"reply": reply, "user_emotion": user_emotion_payload}
                yield f"event: reply_done\ndata: {_json.dumps(reply_payload)}\n\n"

                turn_state.set_status("synthesizing")
                cancel_check()
                audio_url = ""
                sophia_emotion = None
                mock_audio = False
                try:
                    audio_bytes = synthesize_inworld(
                        reply,
                        cancel_check=cancel_check,
                    )
                    cancel_check()
                    file_name = f"sophia_{int(time.time() * 1000)}.mp3"
                    audio_url = supabase_service.upload_audio_and_get_url(
                        audio_bytes, file_name
                    )
                    try:
                        mock_audio = (
                            audio_bytes.startswith(b"ID3mock")
                            or len(audio_bytes) < 2048
                        )
                    except Exception:
                        mock_audio = False
                    cancel_check()
                    sophia_emotion = analyze_emotion_audio(audio_bytes)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Synthesis or upload failed in text_chat_stream")

                payload = {
                    "audio_url": audio_url,
                    "sophia_emotion": (
                        sophia_emotion.model_dump() if sophia_emotion else None
                    ),
                    "mock_audio": mock_audio,
                    "user_emotion": user_emotion_payload,
                }

                _record_text_stream_turn(
                    session_identifier,
                    body.message,
                    reply,
                    user_emotion_payload,
                    sophia_emotion,
                    supabase_token,
                )
                turn_state.set_status("completed")
                yield f"event: audio_url\ndata: {_json.dumps(payload)}\n\n"

            except asyncio.CancelledError:
                logger.info("Streaming text chat turn %s cancelled", turn_state.turn_id)
                raise
            except Exception as e:
                logger.exception("Streaming text chat failed")
                import json as _json

                error_payload = _json.dumps({"detail": str(e)})
                yield f"event: error\ndata: {error_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": int(time.time())}


@app.get("/memory/{session_id}")
async def get_memory(
    session_id: str,
    supabase_token: str = Depends(verify_api_key),
):
    """Get conversation memory for a session"""
    try:
        context = memory_manager.get_context_for_llm(
            session_id, access_token=supabase_token
        )

        return {"session_id": session_id, "context": context, "timestamp": time.time()}

    except Exception as e:
        logger.error(f"Failed to get memory for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve memory")


@app.post("/evaluation/force/{session_id}")
async def force_evaluate_conversation(
    session_id: str,
    supabase_token: str = Depends(verify_api_key),
):
    """Force evaluation of a specific conversation"""
    try:
        from app.services.evaluations import evaluation_manager

        report = evaluation_manager.force_evaluate_conversation(session_id)

        if report is None:
            raise HTTPException(
                status_code=404,
                detail=f"No active conversation found for session {session_id}",
            )

        return {
            "message": "Conversation evaluation completed",
            "session_id": session_id,
            "evaluation_report": {
                "total_messages": report.total_messages,
                "conversation_duration_minutes": round(
                    report.conversation_duration / 60, 2
                ),
                "ragas_average": report.ragas_metrics.average_score
                if report.ragas_metrics
                else None,
                "phoenix_evaluations": len(report.phoenix_metrics),
                "drift_alert": report.drift_alert,
                "confidence_change": f"{report.baseline_confidence:.2f} -> {report.current_confidence:.2f}",
            },
            "timestamp": time.time(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to force evaluate conversation {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to evaluate conversation")


@app.get("/evaluation/status")
async def get_evaluation_status(
    supabase_token: str = Depends(verify_api_key),
):
    """Get current evaluation system status"""
    try:
        from app.services.evaluations import evaluation_manager

        active_count = evaluation_manager.get_active_conversation_count()

        # Get status of all active conversations
        active_conversations = []
        for session_id in evaluation_manager.active_conversations.keys():
            status = evaluation_manager.get_conversation_status(session_id)
            if status:
                active_conversations.append(status)

        return {
            "active_conversations_count": active_count,
            "active_conversations": active_conversations,
            "conversation_timeout_minutes": evaluation_manager.conversation_timeout
            / 60,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Failed to get evaluation status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get evaluation status")


@app.post("/evaluation/check-finished")
async def check_finished_conversations(
    supabase_token: str = Depends(verify_api_key),
):
    """Manually check for and evaluate finished conversations"""
    try:
        from app.services.evaluations import evaluation_manager

        reports = evaluation_manager.check_and_evaluate_finished_conversations()

        evaluation_summaries = []
        for report in reports:
            evaluation_summaries.append(
                {
                    "session_id": report.session_id,
                    "total_messages": report.total_messages,
                    "conversation_duration_minutes": round(
                        report.conversation_duration / 60, 2
                    ),
                    "ragas_average": report.ragas_metrics.average_score
                    if report.ragas_metrics
                    else None,
                    "phoenix_evaluations": len(report.phoenix_metrics),
                    "drift_alert": report.drift_alert,
                }
            )

        return {
            "message": f"Evaluated {len(reports)} finished conversations",
            "evaluations_completed": len(reports),
            "evaluation_summaries": evaluation_summaries,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Failed to check finished conversations: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to check finished conversations"
        )


@app.post("/admin/reload-prompts")
async def reload_prompts(
    supabase_token: str = Depends(verify_api_key),
):
    """Hot reload system prompts from disk (Task #42597)"""
    try:
        from app.services.prompt_composer import prompt_composer

        success = prompt_composer.reload_prompts()
        status = prompt_composer.get_reload_status()

        if success:
            return {
                "message": "Prompts reloaded successfully",
                "status": status,
                "timestamp": time.time(),
            }
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "message": "Prompts reload failed or incomplete",
                    "status": status,
                    "timestamp": time.time(),
                },
            )

    except Exception as e:
        logger.error(f"Failed to reload prompts: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to reload prompts: {str(e)}"
        )


@app.get("/admin/memo-metrics")
async def get_memo_metrics(
    supabase_token: str = Depends(verify_api_key),
):
    """Get MemO performance metrics (Task #42597)"""
    try:
        from app.services.memo import memo_client

        metrics = memo_client.get_metrics()

        return {
            "memo_enabled": memo_client.enabled,
            "metrics": metrics,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Failed to get MemO metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@app.post("/admin/run-migration")
async def run_migration(
    supabase_token: str = Depends(verify_api_key),
):
    """Run user_memories table migration (Task #42597)"""
    try:
        import psycopg
        from pathlib import Path

        migration_file = Path("user_memories_migration.sql")
        if not migration_file.exists():
            raise HTTPException(status_code=404, detail="Migration file not found")

        # Read migration SQL
        with open(migration_file, "r") as f:
            migration_sql = f.read()

        # Get DB connection string from settings
        settings = get_settings()
        db_dsn = settings.SUPABASE_DB_DSN

        if not db_dsn:
            raise HTTPException(
                status_code=500, detail="SUPABASE_DB_DSN not configured"
            )

        # Execute migration
        conn = psycopg.connect(db_dsn)
        cursor = conn.cursor()

        try:
            cursor.execute(migration_sql)
            conn.commit()

            # Verify table exists
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE tablename = 'user_memories'"
            )
            result = cursor.fetchone()

            if result:
                # Get table structure
                cursor.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = 'user_memories'
                    ORDER BY ordinal_position
                """)
                columns = cursor.fetchall()

                return {
                    "message": "Migration executed successfully",
                    "table_exists": True,
                    "columns": [{"name": col[0], "type": col[1]} for col in columns],
                    "timestamp": time.time(),
                }
            else:
                return {
                    "message": "Migration executed but table not found",
                    "table_exists": False,
                    "timestamp": time.time(),
                }

        except Exception as e:
            conn.rollback()
            error_str = str(e).lower()
            if "already exists" in error_str:
                return {
                    "message": "Migration already applied (table exists)",
                    "table_exists": True,
                    "timestamp": time.time(),
                }
            else:
                raise

        finally:
            cursor.close()
            conn.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to run migration: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
