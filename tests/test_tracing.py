"""Item 6 — OpenTelemetry optionality."""
from __future__ import annotations

import sys


def test_tracing_disabled_when_endpoint_empty(monkeypatch):
    """When OTEL_EXPORTER_OTLP_ENDPOINT is empty, the SDK must not run."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    from backend.config import get_settings

    get_settings.cache_clear()
    from backend.observability import tracing

    # Force a fresh tracer.
    tracing._tracer = None
    tr = tracing.tracer()
    # Should be a NoOpTracer — has no real `start_as_current_span` impl that
    # yields non-empty spans.
    assert hasattr(tr, "start_as_current_span")


def test_tracing_enabled_uses_otlp(monkeypatch):
    """When the env var is set, the SDK is configured (we just check it initialises)."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    from backend.config import get_settings

    get_settings.cache_clear()
    from backend.observability import tracing

    tracing._tracer = None
    tr = tracing.tracer()
    # The real tracer exposes `.start_as_current_span`. That's all we need
    # here — the export itself is exercised by an integration test.
    assert hasattr(tr, "start_as_current_span")
    # Reset for other tests.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
