# Sophia Voice Conversation Technical Process

## Scope
This document describes how the Sophia backend ingests user input, generates answers, and returns multimodal responses for the DeFi assistant. It focuses on the production pipeline that powers `POST /defi-chat`, the streaming variants, and supporting services such as memory, RAG, observability, and persistence.

## High-Level Architecture
- **FastAPI application** (`main.py`) exposes REST, SSE, and WebSocket interfaces. It configures CORS, API-key auth, rate limiting, GDPR consent enforcement, and OpenTelemetry instrumentation.
- **LangGraph orchestration** (`app/langgraph_nodes.py`) coordinates the core voice pipeline with reusable nodes for audio ingestion, intent analysis, response generation, TTS, and evaluation logging.
- **AI services** (`app/services/`) wrap external providers:
  - Speech-to-text and LLM generation via Mistral Voxtral (`mistral.py`, `voxtral_large.py`).
  - Emotion analysis through Phoenix + Google Gemini (`emotion.py`).
  - DeFi retrieval augmented generation using SentenceTransformer embeddings (`rag.py`).
  - TTS through Inworld API with streaming support (`tts.py`).
- **Stateful helpers** manage conversation memory (`memory.py`), evaluation (`evaluations.py`), and shared service singletons (`shared_services.py`).
- **Persistence layer** (`supabase.py`) writes session and emotion data, and hosts audio artifacts in Supabase storage.

## API Entry Points
| Endpoint | Mode | Primary pipeline |
| --- | --- | --- |
| `POST /defi-chat` | HTTP | Full LangGraph turn processing with evaluation data capture. |
| `POST /defi-chat/stream` | Server-Sent Events | Legacy STT + streaming LLM with opportunistic Voxtral streaming. |
| `POST /text-chat` | HTTP | Text-only LangGraph execution (skips audio ingestion). |
| `POST /chat` | HTTP | Legacy audio → STT → LLM → TTS path without LangGraph. |
| `POST /transcribe`, `/generate-response`, `/synthesize` | HTTP | Individual building blocks for transcription, text reply, and audio synthesis. |
| `WS /ws/voice` | WebSocket | Real-time bi-directional pipeline with incremental ASR, streaming LLM, and streaming TTS chunks. |

All protected endpoints require a valid `Bearer` token (`APIKeyMiddleware` + `verify_api_key`) and respect a configurable rate limit (`settings.API_RATE_LIMIT`). Conversational routes and the voice WebSocket also enforce GDPR consent via `require_consent`, which checks the `X-Discord-Id` header against Supabase records.

## Request Lifecycle (`POST /defi-chat`)
1. **Ingress and validation** (`main.py:425`):
   - `APIKeyMiddleware` verifies the Authorization header and `require_consent` ensures the caller has accepted data processing.
   - Check file extension, read bytes, generate/accept a `session_id`.
   - Pass audio bytes to `LangGraphService.process_conversation`.
2. **Audio ingestion** (`AudioIngestor`, `app/langgraph_nodes.py:47`):
   - Prefer a shared `HybridVoxtralService` instance (`shared_services.py`) to run the unified Voxtral Large pipeline.
   - Extract transcript and user emotion; record fallback reasons in `state["fallback_used"]`.
   - Fall back to legacy STT (`transcribe_audio_with_voxtral`) and ultimately to Whisper if Voxtral Large fails or returns insufficient speech.
3. **Intent analysis** (`IntentAnalyzer`, `app/langgraph_nodes.py:133`):
   - Rule-based keyword classifier categorizes the transcript into `defi_question`, `emotional_support`, or `small_talk`.
4. **Context construction** (`ResponseGenerator`, `app/langgraph_nodes.py:169`):
   - Retrieve short-term memory from Redis/Supabase via `memory_manager.get_context_for_llm`.
   - For DeFi questions, query the RAG knowledge base (`rag_system.get_context_for_llm`) built from `SentenceTransformer` embeddings.
   - Build a structured prompt for Voxtral Large or legacy LLMs that includes user emotion, prior topics, intent, and retrieved knowledge.
5. **Response generation**:
   - **Primary**: Voxtral Large unified audio-to-text response (`HybridVoxtralService.generate_response`).
   - **Fallbacks**: legacy text-only LLM (`generate_llm_reply`), then intent-aware Claude prompt if Mistral fails, finishing with rule-based tips.
6. **Text-to-speech and Sophia emotion** (`TTSNode`, `app/langgraph_nodes.py:365`):
   - Call Inworld TTS; store MP3 to Supabase Storage via `upload_audio_and_get_url`.
   - Re-run Phoenix audio emotion analysis on the generated speech.
   - Fallback to alternative TTS routines or a neutral placeholder if Inworld is unavailable.
7. **Evaluation logging and memory update** (`EvalLogger`, `app/langgraph_nodes.py:525`):
   - Capture latency, emotions, fallback metadata, and text lengths.
   - Update conversational memory (`memory_manager.update_session_memory`) with the new turn, trimming to the last 3 exchanges.
8. **Return payload**: `LangGraphService` converts the final state into `DefiChatResponse`, including evaluation status and fallback usage.
9. **Persistence** (`main.py:456`):
   - Insert conversation summary into `conversation_sessions` before referencing it from `emotion_scores` (avoids foreign-key violations).
   - Store user and Sophia emotion snapshots using a fixed test ID when no authenticated user is provided.
10. **Evaluation triggers** (`langgraph_service.py:18`):
    - Collected query/answer/audio pairs are buffered in `EvaluationManager`.
    - A background thread runs `check_and_run_evaluations`, invoking Phoenix drift checks and simplified RAGAS scoring once the conversation times out.

## LangGraph Node Responsibilities
- `AudioIngestor`: Handles STT path selection, emotion detection, and emergency fallbacks.
- `IntentAnalyzer`: Supplies routing hints for memory and prompt building.
- `ResponseGenerator`: Chooses Voxtral Large or legacy LLM, injects memory/RAG context, and records failover reasons.
- `TTSNode`: Produces playback audio, uploads to storage, and measures Sophia's tone.
- `EvalLogger`: Consolidates telemetry for downstream analytics and feeds `memory_manager`.

The state object (`GraphState`) carries audio bytes, transcript, emotions, intent, context, reply, TTS assets, and fallback flags throughout the graph.

## Streaming Pipelines
- **`POST /defi-chat/stream`** (`main.py:470`):
  - Pre-reads the upload to avoid file-handle closure.
  - Emits `transcript`, incremental `token`, `reply_done`, and `audio_url` SSE events.
  - Prefers Voxtral audio streaming (`stream_generate_reply_from_audio`); otherwise uses legacy STT + text streaming, then synthesizes audio once the text reply is finalized.
- **`WS /ws/voice`** (`main.py:608`):
  - Maintains a real-time loop that accepts framed audio chunks, debounces voice activity, and streams partial transcripts.
  - Uses the same LangGraph components to recover context but streams tokens sentence-by-sentence, interleaving `synthesize_inworld_stream` PCM chunks for low-latency playback.
  - Persists a summary conversation on disconnect.

## Supporting Services
- **Memory** (`memory.py`):
  - Uses Redis when available with a one-hour TTL, falling back to in-process storage.
  - Persists summaries to Supabase for long-term retrieval and to hydrate future LangGraph runs.
- **RAG** (`rag.py`):
  - Loads a curated DeFi FAQ list, embeds each question with `all-MiniLM-L6-v2`, and performs cosine-similarity lookup with a 0.7 threshold.
- **Evaluations** (`evaluations.py`):
  - `EvaluationManager` aggregates conversation data, computes simplified RAGAS metrics, tracks Phoenix emotion outputs, and raises drift alerts if confidence drops by more than 20%.
  - `PhoenixDriftMonitor` wraps `analyze_emotion_audio` to provide baseline tracking.
- **Shared services** (`shared_services.py`):
  - Lazily instantiates `HybridVoxtralService` once per process to avoid redundant Voxtral Large initialization and rate-limit issues.

## Persistence and Storage
- **Supabase REST** (`supabase.py`):
  - Provides idempotent audio uploads (`upload_audio_and_get_url`) with automatic overwrite, and REST inserts into `conversation_sessions` and `emotion_scores`.
  - Derives stable UUIDs from the `X-Discord-Id` header so conversation rows align with Supabase RLS policies; falls back to a configured default only when no identity is present (e.g., service tests).
  - SQL script [`enable_rls_policies.sql`](./enable_rls_policies.sql) enables row-level security for `conversation_sessions` and `emotion_scores`, granting end-users access only to their own rows while the service role retains administrative privileges.
- **Audio artifacts**: Stored under `SUPABASE_BUCKET_AUDIO` with an `uploads/` prefix; URLs are returned to the client in the response payload.
- **Conversation memory**: Persisted in Supabase tables for later retrieval and analytics, even if Redis is down.

## Observability
- **OpenTelemetry** (`main.py:24`):
  - Configures `TracerProvider` with resource metadata and optional OTLP exporter.
  - Wraps major sections of `/chat` with span instrumentation (`stt_transcription`, `llm_generation`, `tts_synthesis_upload`, emotion spans) and records latency metrics.
- **Logging**:
  - Consistent structured logging across services, including fallback reasons and external API payload lengths.
- **Evaluation reports**:
  - `EvaluationManager` produces aggregated metrics (average faithfulness/relevance/correctness, emotion distributions, drift indicators) for dashboards.

## Configuration Surface (`app/config.py`)
| Setting | Purpose |
| --- | --- |
| `MISTRAL_API_KEY` | Required for Voxtral STT/LLM operations. |
| `INWORLD_API_KEY` | Basic-auth token for Inworld TTS and streaming. |
| `GOOGLE_API_KEY` | Enables Phoenix + Gemini audio emotion analysis. |
| `OPENAI_API_KEY` | Whisper transcription and Boson/OpenAI TTS fallback. |
| `SUPABASE_URL`, `SUPABASE_KEY` | REST client credentials and storage access. |
| `SUPABASE_BUCKET_AUDIO`, `SUPABASE_AUDIO_PREFIX` | Audio storage configuration. |
| `SUPABASE_DB_DSN` | Optional direct SQL path for inserts. |
| `SUPABASE_DEFAULT_USER_ID` | Optional UUID used for test inserts when no authenticated user is provided (must not be all zeros). |
| `REDIS_*` | Session memory cache host, port, database. |
| `OTEL_EXPORTER_OTLP_*` | External telemetry export endpoint and headers. |
| `API_RATE_LIMIT` | Auth throttling configuration. |
| `APP_ENV` | Application environment (`development`, `staging`, or `production`) used for config validation strictness. |
| `CORS_ALLOWED_ORIGINS` | Comma-separated list of trusted origins for CORS; defaults to localhost hosts in development. |
| `API_PUBLIC_PATHS` | Comma-separated list of HTTP paths that bypass API-key enforcement (e.g., `/health,/docs`). |

Environment variables are loaded via `dotenv` early in process startup to ensure settings are available everywhere.

### Configuration Guardrails
- `validate_settings` runs during application bootstrap, aborting launch if mandatory settings (e.g., Supabase credentials) are missing or malformed.
- Supported environments are `development`, `staging`, and `production`; any other value for `APP_ENV` halts startup.
- In non-production modes missing optional keys trigger warnings so developers know related features will fall back to mocks while still allowing local work.
- Supabase helpers reject the all-zero UUID, falling back to a configured `SUPABASE_DEFAULT_USER_ID` or a generated value to keep data consistent.
- Discord identities are converted to deterministic UUIDs for storage, ensuring RLS policies can match authenticated users without storing raw Discord IDs.

## Error Handling and Fallback Matrix
| Stage | Primary tool | Fallbacks | Failure signals |
| --- | --- | --- | --- |
| Audio ingestion | Voxtral Large (`HybridVoxtralService`) | Legacy Voxtral STT → Whisper → empty transcript guard | API errors, short audio, empty transcript, rate limits |
| LLM response | Voxtral Large unified reply | `generate_llm_reply` (Mistral text) → Claude Haiku → canned safety tips | Exceptions from Voxtral Large or Mistral |
| RAG lookup | SentenceTransformer embeddings | Respond without RAG context; confidence implied in evaluation logs | Model load failure, similarity below threshold |
| TTS | Inworld REST / streaming endpoints | Alternative TTS (OpenAI/Boson) → mock MP3 placeholder | HTTP errors, missing auth, empty audio |
| Emotion analysis | Phoenix + Gemini | Neutral default (0.5 confidence) | Missing Google key, Phoenix errors |
| Persistence | Supabase REST/SQL | Log-and-continue; conversation response still delivered | Network issues, schema errors |
| Streaming | Voxtral audio stream | Legacy STT + text stream → single fallback message | Streaming API errors or zero tokens |

Fallback usage is captured in `GraphState["fallback_used"]` and surfaced in API responses to aid observability.

## Secondary Workflows
- **Legacy `/chat`**: Runs the classic pipeline directly inside the endpoint, wrapping each major task with OpenTelemetry spans and persisting results similarly to `/defi-chat`.
- **Atomic endpoints** (`/transcribe`, `/generate-response`, `/synthesize`): Expose individual stages for testing or batch jobs, reusing the same service modules as the orchestrated flows.
- **Text-only conversations** (`/text-chat`): Bypass audio ingestion, but still benefit from intent detection, memory, RAG, TTS, and evaluation logging.

## Sequence Summary
```
Client audio upload
   ↓
FastAPI endpoint (auth, rate limit, span start)
   ↓
LangGraph nodes:
   AudioIngestor → IntentAnalyzer → ResponseGenerator → TTSNode → EvalLogger
   (memory + RAG consulted along the way)
   ↓
Supabase persistence + evaluation buffering
   ↓
JSON reply with transcript, answer, emotions, audio URL, fallbacks, evaluation status
```

This pipeline allows Sophia to deliver emotion-aware, context-rich DeFi coaching with layered resilience against upstream outages and clear hooks for monitoring and continuous evaluation.

## Module Reference
| Module | Responsibility |
| --- | --- |
| `main.py` | FastAPI application setup, endpoint definitions, OpenTelemetry wiring, and orchestration of legacy chat flows, SSE streaming, and WebSocket voice sessions. |
| `app/config.py` | Centralized settings loader using `dotenv`; exposes cached `Settings` object with API keys, rate limits, Supabase, Redis, and OTLP configuration. |
| `app/config_validation.py` | Startup validation that enforces required environment variables and dev-mode warnings for missing optional keys. |
| `app/deps.py` | Shared FastAPI dependencies for API-key verification, rate limiting (`slowapi`), and GDPR consent enforcement backed by Supabase lookups. |
| `app/langgraph_nodes.py` | Defines `GraphState`, LangGraph nodes (audio ingestion, intent analysis, response generation, TTS, evaluation logging), and the `SophiaLangGraph` orchestrator for audio and text conversations. |
| `app/services/langgraph_service.py` | Thin service wrapper around `SophiaLangGraph` that exposes high-level helpers for REST endpoints, evaluation data collection, and background evaluation triggers. |
| `app/services/shared_services.py` | Singleton manager that lazily provisions `HybridVoxtralService` instances so LangGraph nodes reuse a single Voxtral Large pipeline. |
| `app/services/voxtral_large.py` | Implements Voxtral Large direct audio-to-response workflow, streaming support, and hybrid fallback logic that returns to the legacy STT + LLM stack when necessary. |
| `app/services/mistral.py` | Wraps Mistral SDK for Voxtral transcription, audio-aware response generation, text-only replies, and streaming token emission with rule-based fallbacks. |
| `app/services/emotion.py` | Provides Phoenix + Gemini based sentiment analysis for text and audio, normalizing labels for database constraints and defaulting to neutral when external services fail. |
| `app/services/tts.py` | Integrates with Inworld REST and streaming TTS APIs, including payload cleaning, mock fallbacks, and chunked PCM streaming for WebSocket playback. |
| `app/services/rag.py` | Lazily loads the SentenceTransformer model on first use, caches FAQ embeddings, and performs cosine-similarity retrieval for LangGraph prompts. |
| `app/services/memory.py` | Maintains short-term conversation memory via Redis (with Supabase fallback), extracts conversational topics, and exposes context for LLM prompts. |
| `app/services/evaluations.py` | Collects message-level data, computes simplified RAGAS metrics, evaluates Phoenix emotion confidence, and monitors drift, returning structured evaluation reports. |
| `app/services/db.py` | Optional psycopg-based SQL helpers that write conversation sessions and emotion scores directly when a Supabase DSN is available. |
| `app/services/supabase.py` | Provides `init_supabase` to create a shared Supabase client once, derives stable UUIDs from Discord IDs, enforces non-zero defaults, handles audio uploads, conversation/emotion inserts, consent helpers, and bridges to optional SQL utilities. |
| `app/services/memory.ConversationTurn` & related dataclasses | Data structures used across memory and evaluation components to persist structured conversation metadata. |
| `app/services/langgraph_service.EvaluationManager` | High-level evaluation orchestrator that buffers conversation data from LangGraph, runs asynchronous checks, and tracks active sessions. |
| `tests/` | Contains pytest suites for API endpoints (`test_api.py`, `test_api_endpoints.py`), authentication, LangGraph streaming, TTS configuration, and frontend integration smoke tests. |
| `frontend-nextjs/` | Next.js 14 application with Discord OAuth, consent flows, voice UI, and emotion visualization; deployed separately on Vercel but referenced by backend documentation. |
| `deployment-guide.md`, `Dockerfile*`, `fly.toml`, `render.yaml` | Infrastructure assets covering containerization, Fly.io deployment, Render configuration, and CI-ready deployment instructions. |
