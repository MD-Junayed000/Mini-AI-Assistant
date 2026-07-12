"""Custom exception hierarchy + ERROR_MESSAGES friendly-catalog.

Every error code a user can see maps to a friendly string.
Backend emits structured {error, code, request_id}; the React UI surfaces
the banner from `code`.
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base for all expected application errors."""

    code: str = "internal_error"
    http_status: int = 500

    def __init__(self, message: str = "", **details: Any) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__
        self.details = details


class IngestionError(AppError):
    code = "ingestion_failed"
    http_status = 422


class RetrieverError(AppError):
    code = "retriever_unavailable"
    http_status = 503


class ToolError(AppError):
    code = "tool_unavailable"
    http_status = 502


class LLMError(AppError):
    code = "llm_unavailable"
    http_status = 502


class MemoryError_(AppError):  # avoid shadowing stdlib
    code = "memory_unavailable"
    http_status = 503


class ValidationError(AppError):
    code = "validation_error"
    http_status = 400


class RateLimitError(AppError):
    code = "rate_limited"
    http_status = 429


class RetrieverEmptyError(RetrieverError):
    code = "retriever_empty"
    http_status = 404


# Backwards-compat alias (some call sites did `MemoryError`).
MemoryError = MemoryError_


ERROR_MESSAGES: dict[str, str] = {
    "internal_error": "Something went wrong on our end. Please try again.",
    "validation_error": "The request was malformed. Please check your input and try again.",
    "ingestion_failed": "I couldn't read that document. The file may be corrupted or protected.",
    "retriever_unavailable": "The search service is temporarily unavailable. Please retry in a few seconds.",
    "retriever_empty": "I couldn't find that information in the uploaded documents.",
    "tool_unavailable": "One of the connected tools is temporarily unavailable.",
    "llm_unavailable": "The language service is temporarily down. Please try again in a few seconds.",
    "rate_limited": "You're sending messages too quickly — please wait a moment and retry.",
    "memory_unavailable": "I can't recall our previous conversation right now. Please try again later.",
    "chroma_restart_required": (
        "The vector index is unrecoverable in this process. "
        "Restart the API server, then re-upload your document."
    ),
    "chroma_recovered_retry_ingest": (
        "The vector index was rebuilt on startup. "
        "Click Upload again to index your document."
    ),
    "extract_failed": (
        "I couldn't read that document. The file may be corrupted, "
        "password-protected, or in an unsupported layout."
    ),
    "chroma_unrecoverable": (
        "The vector index is in an unrecoverable state. "
        "Restart the API server, then re-upload your document."
    ),
}


def friendly_message(code: str) -> str:
    """Resolve a code → user-friendly string (with fallback to generic)."""
    return ERROR_MESSAGES.get(code, ERROR_MESSAGES["internal_error"])
