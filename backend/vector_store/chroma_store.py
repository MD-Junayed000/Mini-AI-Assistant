"""ChromaDB client wrapper.

Supports Chroma Cloud (default) and local persistent mode. The same
sentence-transformers model is bound via Chroma's
``SentenceTransformerEmbeddingFunction`` so the vector space is shared with
the local cosine reranker in ``backend.llm.rerank``.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.config import get_settings
from backend.errors import RetrieverError
from backend.observability.logging_config import get_logger
from backend.vector_store.recovery import auto_recover_if_corrupt

log = get_logger("chroma")


@dataclass
class Hit:
    id: str
    text: str
    metadata: dict[str, Any]
    score: float  # cosine similarity in [-1, 1]


def _build_embedding_function():
    """Bind the configured sentence-transformers model to Chroma collections.

    ``SentenceTransformerEmbeddingFunction`` normalizes vectors so cosine
    similarity reduces to a dot product.
    """
    from chromadb.utils import embedding_functions

    s = get_settings()
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=s.hf_embedding_model,
    )


class ChromaStore:
    """Chroma client bound to one collection.

    Supports Chroma Cloud (default) and local persistent mode. The public
    method signatures are identical across backends.

    The class caches one instance per `collection` name (process-wide) so that
    the sentence-transformers model download + Chroma client setup happen
    exactly once. The first `/chat` or `/admin/kb/sources` request pays the
    full cold-start cost; every subsequent request reuses the same store
    (and the same embedding function) so retrieval stays fast.
    """

    _INSTANCES: dict[str, "ChromaStore"] = {}

    @classmethod
    def instance(cls, collection: str | None = None) -> "ChromaStore":
        """Return the cached store for this collection, building it on first use.

        Cheap to call from hot paths; the expensive constructor runs once.
        """
        name = collection or get_settings().chroma_collection
        existing = cls._INSTANCES.get(name)
        if existing is not None:
            return existing
        store = cls(collection=name)
        cls._INSTANCES[name] = store
        return store

    def __init__(self, collection: str | None = None) -> None:
        s = get_settings()
        self._collection_name = collection or s.chroma_collection
        self._use_cloud = s.chroma_use_cloud
        self._persist_dir: Path | None = None
        if self._use_cloud:
            if not s.chroma_api_key or not s.chroma_tenant:
                raise RuntimeError(
                    "Chroma Cloud is enabled (CHROMA_USE_CLOUD=true) but "
                    "CHROMA_API_KEY / CHROMA_TENANT are not set. Copy them "
                    "from https://www.trychroma.com/ into your .env, or set "
                    "CHROMA_USE_CLOUD=false to use the local persistent store."
                )
            import chromadb

            self._client = chromadb.CloudClient(
                api_key=s.chroma_api_key,
                tenant=s.chroma_tenant,
                database=s.chroma_database,
            )
        else:
            # Local persistent mode — used for tests and air-gapped runs.
            self._persist_dir = Path(s.chroma_persist_dir)
            if self._persist_dir.exists():
                auto_recover_if_corrupt(self._persist_dir)
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            import chromadb

            self._client = chromadb.PersistentClient(path=str(self._persist_dir))

        self._embed_fn = _build_embedding_function()
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=self._embed_fn,
        )
        # A half-written local HNSW from a killed previous process segfaults
        # inside chromadb's Rust code with no Python-visible exception, so we
        # probe on first use and rebuild if needed. Cloud mode is fine by
        # construction.
        self._verified_ok = self._use_cloud

    def _recreate_collection(self) -> None:
        """Drop and recreate the collection. Destroys data; last resort."""
        try:
            self._client.delete_collection(self._collection_name)
        except Exception:  # noqa: BLE001 — collection may not exist
            pass
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=self._embed_fn,
        )

    def _self_heal(self) -> bool:
        """Probe the HNSW index and rebuild if it raises. False = still broken."""
        if self._verified_ok:
            return True
        try:
            # A trivial query exercises the HNSW read path that upsert will
            # use for its write path.
            self._collection.query(query_texts=["__healthcheck__"], n_results=1)
        except Exception as exc:  # noqa: BLE001
            log.warning("chroma_collection_unhealthy_rebuilding", error=str(exc))
            try:
                self._recreate_collection()
                self._verified_ok = True
                return True
            except Exception as e2:  # noqa: BLE001
                log.error("chroma_recreate_failed", error=str(e2))
                return False
        self._verified_ok = True
        return True

    async def add_texts(
        self,
        *,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        if not texts:
            return

        def _add() -> None:
            # upsert keeps ingestion idempotent — chunk IDs are deterministic
            # ({stem}::chunk::{i}) so re-ingesting the same source just
            # overwrites existing vectors.
            self._collection.upsert(
                ids=ids,
                documents=texts,
                metadatas=metadatas,
            )

        if not self._verified_ok and not self._self_heal():
            raise RetrieverError("chroma_collection_unrecoverable")
        try:
            await asyncio.to_thread(_add)
        except Exception as e:  # noqa: BLE001
            # Likely transient — reset the verified flag and retry once
            # after a self-heal rebuild.
            log.warning("chroma_upsert_failed_attempting_heal", error=str(e))
            self._verified_ok = False
            if self._self_heal():
                await asyncio.to_thread(_add)
                return
            raise RetrieverError(str(e)) from e

    async def query(self, text: str, top_k: int = 8) -> list[Hit]:
        if not text.strip():
            return []

        def _q() -> dict[str, Any]:
            return self._collection.query(
                query_texts=[text],
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
            # Chroma returns cosine distance; convert to similarity.
            sim = max(-1.0, min(1.0, 1.0 - float(dist)))
            out.append(Hit(id=i, text=d, metadata=m or {}, score=sim))
        return out

    async def count(self) -> int:
        def _c() -> int:
            return self._collection.count()

        return await asyncio.to_thread(_c)

    async def list_sources(self) -> list[dict[str, Any]]:
        """Return one row per distinct `source` metadata value (used by the KB UI)."""
        def _list() -> list[dict[str, Any]]:
            data = self._collection.get(include=["metadatas"])
            counts: dict[str, int] = {}
            for m in data.get("metadatas") or []:
                src = (m or {}).get("source")
                if not src:
                    continue
                counts[src] = counts.get(src, 0) + 1
            return [
                {"source": src, "chunks": n}
                for src, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            ]

        return await asyncio.to_thread(_list)

    async def delete_by_source(self, source: str) -> int:
        """Delete every chunk whose metadata `source` matches exactly. Returns the count removed.

        ``source`` must be the full stored path string returned by ``list_sources()``.
        """
        if not source:
            return 0

        def _del() -> int:
            existing = self._collection.get(
                where={"source": source}, include=[]
            )
            ids = list(existing.get("ids") or [])
            if not ids:
                return 0
            # Batch defensively for Chroma's per-call limits.
            BATCH = 500
            for i in range(0, len(ids), BATCH):
                self._collection.delete(ids=ids[i:i + BATCH])
            return len(ids)

        return await asyncio.to_thread(_del)

    async def clear_all(self) -> int:
        """Remove every chunk in the collection. Returns the deleted count.

        Cheaper than ``reset()`` because the embedding-function binding
        stays intact.
        """
        def _clear() -> int:
            data = self._collection.get(include=[])
            ids = list(data.get("ids") or [])
            if not ids:
                return 0
            BATCH = 500
            for i in range(0, len(ids), BATCH):
                self._collection.delete(ids=ids[i:i + BATCH])
            return len(ids)

        return await asyncio.to_thread(_clear)

    async def reset(self) -> None:
        def _r() -> None:
            self._client.delete_collection(name=self._collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=self._embed_fn,
            )

        await asyncio.to_thread(_r)