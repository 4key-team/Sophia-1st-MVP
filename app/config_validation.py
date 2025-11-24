"""Startup configuration validation for Sophia backend."""

import logging
from typing import Iterable

from app.config import Settings

logger = logging.getLogger("sophia-backend")

MANDATORY_VARS: Iterable[str] = ("SUPABASE_URL",)
PRODUCTION_ONLY_VARS: Iterable[str] = (
    "MISTRAL_API_KEY",
    "INWORLD_API_KEY",
    "GOOGLE_API_KEY",
)
ALLOWED_ENVIRONMENTS = {"development", "staging", "production"}


def _collect_missing(settings: Settings, names: Iterable[str]) -> list[str]:
    missing: list[str] = []
    for name in names:
        if not getattr(settings, name, None):
            missing.append(name)
    return missing


def validate_settings(settings: Settings) -> None:
    """Validate environment configuration and abort on fatal issues.

    In development and staging we allow missing external API keys but emit warnings so
    developers know those features will fall back to mock behaviours.
    """
    env = getattr(settings, "ENVIRONMENT", "development").lower()
    if env not in ALLOWED_ENVIRONMENTS:
        raise SystemExit(
            f"Invalid APP_ENV/ENVIRONMENT value '{env}'. Expected one of {sorted(ALLOWED_ENVIRONMENTS)}."
        )

    missing_core = _collect_missing(settings, MANDATORY_VARS)

    supabase_key = getattr(settings, "SUPABASE_KEY", None)
    anon_key = getattr(settings, "SUPABASE_ANON_KEY", None)

    if not supabase_key:
        missing_core.append("SUPABASE_KEY")

    if not (anon_key or supabase_key):
        missing_core.append("SUPABASE_ANON_KEY")
    if missing_core:
        missing = ", ".join(missing_core)
        raise SystemExit(
            f"Missing required environment variables: {missing}. Please update .env before starting the service."
        )

    if env == "production":
        missing_prod = _collect_missing(settings, PRODUCTION_ONLY_VARS)
        if missing_prod:
            missing = ", ".join(missing_prod)
            raise SystemExit(
                f"Production environment requires the following API keys to be configured: {missing}."
            )
    else:
        # Warn about optional integrations so developers understand fallback behaviour.
        for name in PRODUCTION_ONLY_VARS:
            if not getattr(settings, name, None):
                logger.warning(
                    "Optional config '%s' is not set; related functionality will use mock or degraded behaviour.",
                    name,
                )
