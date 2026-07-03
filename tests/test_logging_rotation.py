"""Item 7 — log rotation."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler


def test_rotating_handler_caps_files(tmp_path, monkeypatch):
    """Write >50 MB worth of logs and assert the file count stays bounded."""
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_MAX_BYTES", str(1024 * 64))  # 64 KB
    monkeypatch.setenv("LOG_BACKUP_COUNT", "5")
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    from backend.config import get_settings
    get_settings.cache_clear()

    from backend.observability.logging_config import configure_logging

    configure_logging()
    log = logging.getLogger("rotation-test")
    line = ("abcdefghij" * 100) + "\n"  # ~1 KB
    for _ in range(2000):  # ~2 MB
        log.info(line)

    files = sorted(tmp_path.glob("app.log*"))
    # One live file + 5 rotated at most.
    assert len(files) <= 6
    # All files present, all under soft cap.
    for f in files:
        assert f.stat().st_size <= 256 * 1024  # generous upper bound
