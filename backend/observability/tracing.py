"""Optional OpenTelemetry — gated by OTEL_EXPORTER_OTLP_ENDPOINT.

Item 6: when the env var is empty, this module is a no-op. When set, it
configures a TracerProvider with an OTLP exporter and a set of named
spans mirroring the request flow.
"""
from __future__ import annotations

from typing import Any

from backend.config import get_settings

_tracer: Any = None


def init_tracing() -> Any:
    """Idempotent OTel setup. Returns the (real or noop) tracer."""
    global _tracer
    if _tracer is not None:
        return _tracer

    settings = get_settings()
    if not settings.otel_enabled:
        # import opentelemetry.trace for the real no-op tracer so callers
        # don't need to guard imports.
        from opentelemetry.trace import NoOpTracer

        _tracer = NoOpTracer()
        return _tracer

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(settings.otel_service_name)
    return _tracer


def tracer() -> Any:
    """Return the configured tracer (init first if needed)."""
    if _tracer is None:
        return init_tracing()
    return _tracer
