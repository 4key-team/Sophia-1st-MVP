"""OpenTelemetry tracer initialization shared across the application."""

from typing import Optional

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import Settings

tracer = None

def _normalize_otlp_endpoint(ep: Optional[str]) -> Optional[str]:
    if not ep:
        return None
    ep = ep.rstrip("/")
    # If caller passed base gateway (e.g., https://otlp-gateway.grafana.net/otlp),
    # add the traces path expected by the HTTP exporter.
    if not ep.endswith("/v1/traces"):
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


def setup_tracer(app: FastAPI, settings: Settings):
    """Initialize a tracer provider and instrument FastAPI, returning the tracer."""
    resource = Resource.create(
        {
            "service.name": "sophia-backend",
            "service.version": "1.0.0",
            "deployment.environment": getattr(settings, "ENVIRONMENT", "staging"),
        }
    )

    provider = TracerProvider(resource=resource)
    otlp_endpoint = _normalize_otlp_endpoint(settings.OTEL_EXPORTER_OTLP_ENDPOINT)
    otlp_headers = _parse_otlp_headers(settings.OTEL_EXPORTER_OTLP_HEADERS)
    if otlp_endpoint:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, headers=otlp_headers)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    return trace.get_tracer("sophia")
