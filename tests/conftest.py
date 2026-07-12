"""Test fixtures shared across the suite."""
from __future__ import annotations

import os
import sys
import pytest
from pathlib import Path

# Make `backend` importable when pytest is run from project root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _env_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Default test env — temp dirs, fake keys."""
    monkeypatch.setenv("OLLAMA_CLOUD_BASE_URL", "https://ollama.test/v1")
    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", "test-key")
    monkeypatch.setenv("OLLAMA_PRIMARY_MODEL", "qwen3.5:122b-cloud")
    monkeypatch.setenv("OLLAMA_FALLBACK_MODEL", "gpt-oss:120b-cloud")
    monkeypatch.setenv("HF_INFERENCE_BASE_URL", "https://router.test/v1")
    monkeypatch.setenv("HF_INFERENCE_API_KEY", "test-hf")
    monkeypatch.setenv("CHROMA_USE_CLOUD", "false")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("BM25_CACHE_PATH", str(tmp_path / "chroma" / "bm25.pkl"))
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017/test")
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "5")
    monkeypatch.setenv("HEALTH_CACHE_TTL_SECONDS", "10")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    # Clear settings cache so each test sees fresh values.
    from backend.config import get_settings
    get_settings.cache_clear()
    yield


@pytest.fixture()
def orders_fixture(tmp_path: Path) -> Path:
    p = tmp_path / "orders.json"
    p.write_text(Path("tests/fixtures/orders.json").read_text(encoding="utf-8"), encoding="utf-8")
    # Point the loader at the test directory.
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        yield p
    finally:
        os.chdir(cwd)
