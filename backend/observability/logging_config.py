"""Centralised structlog setup — JSON logs, rotating file handler, redactor.

v2.2 hardening items landed here:
  - Item 4: redactor processor wired into the chain.
  - Item 7: RotatingFileHandler (50 MB x 5) for the file sink.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

import structlog

from backend.config import get_settings
from backend.observability.redactor import redact_processor


def configure_logging() -> None:
    """Configure structlog + stdlib logging. Idempotent."""
    settings = get_settings()
    log_path = Path(settings.log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    file_path = log_path / "app.log"

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # stdlib root logger — structlog will funnel through this.
    root = logging.getLogger()
    root.setLevel(level)
    # Clear any prior handlers (FastAPI reloads etc.).
    for h in list(root.handlers):
        root.removeHandler(h)

    rotating = logging.handlers.RotatingFileHandler(
        filename=file_path,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    stream = logging.StreamHandler(sys.stderr)

    formatter = logging.Formatter("%(message)s")
    rotating.setFormatter(formatter)
    stream.setFormatter(formatter)

    root.addHandler(rotating)
    root.addHandler(stream)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog bound logger."""
    return structlog.get_logger(name)
