"""Application configuration sourced from environment variables.

All settings are centralised here so the rest of the codebase can stay
declarative. Loaded once at import time via lru_cache.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed settings loaded from .env / process env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    ollama_cloud_base_url: str = "https://ollama.com/v1"
    ollama_cloud_api_key: str = "your-ollama-cloud-key"
    ollama_primary_model: str = "gpt-oss:20b"
    ollama_fallback_model: str = "gpt-oss:120b"
    ollama_timeout_seconds: int = 30

    hf_inference_base_url: str = "https://router.huggingface.co/v1"
    hf_inference_api_key: str = "your-hf-token"
    hf_embedding_model: str = "BAAI/bge-small-en-v1.5"
    vision_provider: Literal["hf", "ollama"] = "ollama"
    hf_vision_model: str = "google/gemma-3-27b-it"
    ollama_vision_model: str = "gemma4:31b-cloud"

    chroma_use_cloud: bool = True
    chroma_host: str = "api.trychroma.com"
    chroma_api_key: str = ""
    chroma_tenant: str = ""
    chroma_database: str = "mini_ai"
    chroma_collection: str = "mini_ai_kb"
    chroma_persist_dir: str = "./.chroma"
    bm25_cache_path: str = "./.chroma/bm25.pkl"

    mongodb_uri: str = "mongodb+srv://user:pass@cluster0.mongodb.net/?appName=mini-ai"
    mongodb_db: str = "mini_ai"
    mongodb_collection: str = "messages"

    rate_limit_per_min: int = 30
    health_cache_ttl_seconds: int = 10
    max_context_chars: int = 8_000
    confidence_gate_threshold: float = 0.62
    cors_origins: str = "*"
    rerank_disabled: bool = False

    log_dir: str = "./logs"
    log_level: str = "INFO"
    log_max_bytes: int = 50 * 1024 * 1024
    log_backup_count: int = 5

    otel_exporter_otlp_endpoint: str = ""
    otel_exporter_otlp_headers: str = ""   # e.g. "x-honeycomb-team=abc123"
    otel_service_name: str = "mini-ai-assistant"

    @property
    def log_path(self) -> Path:
        return Path(self.log_dir) / "app.log"

    @property
    def otel_enabled(self) -> bool:
        return bool(self.otel_exporter_otlp_endpoint)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor."""
    return Settings()
