"""Friendly error catalog + global handler."""
from backend.errors import (
    AppError,
    ERROR_MESSAGES,
    IngestionError,
    LLMError,
    MemoryError_,
    RateLimitError,
    RetrieverEmptyError,
    ValidationError,
    friendly_message,
)


def test_catalog_covers_all_codes():
    needed = {
        "internal_error",
        "validation_error",
        "ingestion_failed",
        "retriever_unavailable",
        "retriever_empty",
        "tool_unavailable",
        "llm_unavailable",
        "rate_limited",
        "memory_unavailable",
    }
    assert needed.issubset(ERROR_MESSAGES.keys())


def test_friendly_message_unknown_returns_generic():
    assert "Something went wrong" in friendly_message("nonexistent_code")


def test_http_status_codes_are_sane():
    assert IngestionError().http_status == 422
    assert LLMError().http_status == 502
    assert RateLimitError().http_status == 429
    assert ValidationError().http_status == 400
    assert RetrieverEmptyError().http_status == 404
    assert MemoryError_().http_status == 503


def test_error_carries_details():
    e = ValidationError("bad thing", field="foo")
    assert e.message == "bad thing"
    assert e.details == {"field": "foo"}


def test_app_error_default_code():
    e = AppError("x")
    assert e.code == "internal_error"
    assert e.http_status == 500
