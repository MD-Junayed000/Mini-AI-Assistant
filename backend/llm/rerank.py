"""HF cross-encoder reranker.

We send (query, [candidate, ...]) to the HF inference router and read back
relevance scores. Cheap compared to a second LLM call.
"""
from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.config import get_settings
from backend.observability.logging_config import get_logger
from backend.observability.metrics import STAGE_LATENCY, RERANK_TOP_SCORE

log = get_logger("rerank")


class _Retryable(Exception):
    pass


class HFReranker:
    def __init__(self) -> None:
        s = get_settings()
        self._url = f"{s.hf_inference_base_url.rstrip('/')}/rerank"
        self._model = s.hf_rerank_model
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
    async def rerank(self, query: str, candidates: list[str], top_k: int) -> list[tuple[int, float]]:
        if not candidates:
            return []
        payload = {
            "model": self._model,
            "query": query,
            "inputs": candidates,
            "top_k": min(top_k, len(candidates)),
            "return_documents": False,
        }
        try:
            with STAGE_LATENCY.labels(stage="rerank").time():
                async with httpx.AsyncClient(timeout=self._timeout) as cx:
                    r = await cx.post(self._url, headers=self._headers, json=payload)
                    r.raise_for_status()
                    data = r.json()
        except httpx.HTTPError as e:
            raise _Retryable(str(e)) from e

        # Shape: {"results": [{"index": int, "relevance_score": float}, ...]}
        try:
            results = sorted(data["results"], key=lambda x: x["index"])
            pairs = [(item["index"], float(item["relevance_score"])) for item in results]
        except (KeyError, TypeError, ValueError) as e:
            log.error("rerank_unexpected_shape", payload=list(data.keys()))
            raise _Retryable("rerank_unexpected_shape") from e

        # Track the top score for dashboards.
        if pairs:
            best = max(p[1] for p in pairs)
            RERANK_TOP_SCORE.observe(best)
        return pairs