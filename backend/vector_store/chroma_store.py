"""ChromaDB persistent client wrapper.

We compute embeddings via HF Inference and pass them in — Chroma's default
embedding function is intentionally avoided so we have one source of truth.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.config import get_settings
from backend.errors import RetrieverError
from backend.llm.embeddings import HFEmbeddingClient
from backend.observability.logging_config import get_logger

log = get_logger("chroma")


@dataclass
class Hit:
    id: str
    text: str
    metadata: dict[str, Any]
    score: float  # cosine similarity in [-1, 1]


class ChromaStore:
    """Persistent Chroma client bound to one collection."""

    def __init__(self, collection: str | None = None) -> None:
        s = get_settings()
        self._collection_name = collection or s.chroma_collection
        Path(s.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
        import chromadb

        self._client = chromadb.PersistentClient(path=s.chroma_persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._embedder = HFEmbeddingClient()

    async def add_texts(
        self,
        *,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        if not texts:
            return
        # Batch-embed (HF supports batches; we cap at 64 to stay under
        # request size limits).
        BATCH = 64
        vectors: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            vectors.extend(await self._embedder.embed(texts[i : i + BATCH]))

        def _add() -> None:
            self._collection.add(
                ids=ids,
                embeddings=vectors,
                documents=texts,
                metadatas=metadatas,
            )

        await asyncio.to_thread(_add)

    async def query(self, text: str, top_k: int = 8) -> list[Hit]:
        if not text.strip():
            return []
        vector = await self._embedder.embed_one(text)

        def _q() -> dict[str, Any]:
            return self._collection.query(
                query_embeddings=[vector],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )

        try:
            data = await asyncio.to_thread(_q)
        except Exception as e:  # noqa: BLE001
            log.error("chroma_query_failed", error=str(e))
            raise RetrieverError(str(e)) from e

        ids = (data.get("ids") or [[]])[0]
        docs = (data.get("documents") or [[]])[0]
        metas = (data.get("metadatas") or [[]])[0]
        dists = (data.get("distances") or [[]])[0]
        out: list[Hit] = []
        for i, d, m, dist in zip(ids, docs, metas, dists):
            # Chroma returns cosine *distance*; convert to similarity.
            sim = max(-1.0, min(1.0, 1.0 - float(dist)))
            out.append(Hit(id=i, text=d, metadata=m or {}, score=sim))
        return out

    async def count(self) -> int:
        def _c() -> int:
            return self._collection.count()

        return await asyncio.to_thread(_c)

    async def reset(self) -> None:
        def _r() -> None:
            self._client.delete_collection(name=self._collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )

        await asyncio.to_thread(_r)