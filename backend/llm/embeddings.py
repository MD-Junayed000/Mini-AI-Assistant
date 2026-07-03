"""Hugging Face Inference embedding client.

BAAI/bge-small-en-v1.5 produces 384-d normalised vectors. We hit the
HF router endpoint and trim to top N tokens if the result is truncated.
"""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.config import get_settings
from backend.observability.logging_config import get_logger
from backend.observability.metrics import STAGE_LATENCY

log = get_logger("embeddings")


class _Retryable(Exception):
    pass


class HFEmbeddingClient:
    def __init__(self) -> None:
        s = get_settings()
        self._url = f"{s.hf_inference_base_url.rstrip('/')}/embeddings"
        self._model = s.hf_embedding_model
        self._headers = {
            "Authorization": f"Bearer {s.hf_inference_api_key}",
            "Content-Type": "application/json",
        }
        self._timeout = 30

    @retry(
        retry=retry_if_exception_type(_Retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=4),
        reraise=True,
    )
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload: dict[str, Any] = {
            "model": self._model,
            "input": texts,
            "encoding_format": "float",
        }
        try:
            with STAGE_LATENCY.labels(stage="embed").time():
                async with httpx.AsyncClient(timeout=self._timeout) as cx:
                    r = await cx.post(self._url, headers=self._headers, json=payload)
                    r.raise_for_status()
                    data = r.json()
        except httpx.HTTPError as e:
            raise _Retryable(str(e)) from e

        # OpenAI-compatible: {data: [{embedding: [...]}, ...]}
        try:
            return [item["embedding"] for item in data["data"]]
        except (KeyError, TypeError) as e:
            log.error("embeddings_unexpected_shape", payload=list(data.keys()))
            raise _Retryable("embeddings_unexpected_shape") from e

    async def embed_one(self, text: str) -> list[float]:
        out = await self.embed([text])
        return out[0]