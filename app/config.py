"""Configuration loader that exposes environment-driven settings to the backend."""

import os
from functools import lru_cache
from typing import Optional, List

try:
    from dotenv import load_dotenv, find_dotenv
except ImportError:  # pragma: no cover - optional in some test environments

    def load_dotenv(*_args, **_kwargs):
        return False

    def find_dotenv(*_args, **_kwargs):
        return ""


# Load .env as early as possible so Settings reads populated values.
# find_dotenv() will search parent directories to locate the .env file.
load_dotenv(find_dotenv(), override=False)


class Settings:
    APP_NAME: str = "Sophia Voice Backend"
    API_RATE_LIMIT: str = os.getenv("API_RATE_LIMIT", "30/minute")
    ENVIRONMENT: str = os.getenv(
        "APP_ENV", os.getenv("ENVIRONMENT", "development")
    ).lower()

    # Auth
    API_KEYS: List[str] = [
        k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()
    ]
    REQUIRE_CONSENT: str = os.getenv("REQUIRE_CONSENT", "true")

    # External services
    MISTRAL_API_KEY: Optional[str] = os.getenv("MISTRAL_API_KEY")
    MISTRAL_API_BASE: str = os.getenv("MISTRAL_API_BASE", "https://api.mistral.ai")
    INWORLD_API_KEY: Optional[str] = os.getenv("INWORLD_API_KEY")  # Base64 Basic token
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY")

    # Redis for memory caching
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))

    # Supabase (HTTP client for storage/REST)
    SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL")
    SUPABASE_KEY: Optional[str] = os.getenv("SUPABASE_KEY")
    SUPABASE_ANON_KEY: Optional[str] = os.getenv("SUPABASE_ANON_KEY")
    SUPABASE_BUCKET_AUDIO: str = os.getenv("SUPABASE_BUCKET_AUDIO", "audio")
    SUPABASE_AUDIO_PREFIX: str = os.getenv("SUPABASE_AUDIO_PREFIX", "uploads/")
    SUPABASE_SIGNED_URL_TTL: int = int(os.getenv("SUPABASE_SIGNED_URL_TTL", "3600"))

    # Optional: direct Postgres via Transaction Pooler
    SUPABASE_DB_DSN: Optional[str] = os.getenv("SUPABASE_DB_DSN")
    SUPABASE_DEFAULT_USER_ID: Optional[str] = os.getenv("SUPABASE_DEFAULT_USER_ID")

    # MemO Memory (Task #42597)
    MEMO_ENABLED: bool = os.getenv("MEMO_ENABLED", "true").lower() == "true"
    MEMO_TOP_K: int = int(os.getenv("MEMO_TOP_K", "5"))
    MEMO_SIMILARITY_THRESHOLD: float = float(
        os.getenv("MEMO_SIMILARITY_THRESHOLD", "0.7")
    )
    MEMO_EMBEDDING_MODEL: str = os.getenv(
        "MEMO_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )

    # OpenTelemetry (OTLP HTTP exporter)
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    OTEL_EXPORTER_OTLP_HEADERS: Optional[str] = os.getenv("OTEL_EXPORTER_OTLP_HEADERS")

    _cors_raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if _cors_raw:
        cors_values = [
            origin.strip() for origin in _cors_raw.split(",") if origin.strip()
        ]
    else:
        # Safe defaults for local development; production should set env var explicitly.
        cors_values = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    CORS_ALLOWED_ORIGINS: List[str] = cors_values

    _public_raw = os.getenv(
        "API_PUBLIC_PATHS",
        "/,/health,/docs,/openapi.json,/api",
    )
    API_PUBLIC_PATHS: List[str] = [
        path.strip() for path in _public_raw.split(",") if path.strip()
    ]

    # Emotional RAG (S2 Part 8)
    EMO_RAG_PROVIDER: str = os.getenv("EMO_RAG_PROVIDER", "static").lower()
    EMOTIONAL_RAG_SERVICE_URL: Optional[str] = os.getenv("EMOTIONAL_RAG_SERVICE_URL")
    EMOTIONAL_RAG_TIMEOUT_SECONDS: float = float(
        os.getenv("EMOTIONAL_RAG_TIMEOUT_SECONDS", "0.3")
    )

    # Affect snapshot / Phoenix background
    AFFECT_SNAPSHOT_TTL_SECONDS: int = int(
        os.getenv("AFFECT_SNAPSHOT_TTL_SECONDS", "300")
    )
    PHOENIX_BG_TIMEOUT_SECONDS: float = float(
        os.getenv("PHOENIX_BG_TIMEOUT_SECONDS", "12.0")
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
