"""Top-level ingestion: PDF → chunks → Chroma + BM25 + metric increments."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from backend.config import get_settings
from backend.ingestion.chunker import chunk_text
from backend.ingestion.docling_pipeline import extract, extract_with_backend
from backend.observability.logging_config import get_logger
from backend.observability.metrics import INGEST_DOCUMENTS, STAGE_LATENCY
from backend.vector_store.chroma_store import ChromaStore
from backend.vector_store.bm25_index import BM25Index

log = get_logger("ingest")


async def ingest_file(
    path: Path,
    *,
    collection: str | None = None,
    doc_id_prefix: str | None = None,
) -> dict[str, Any]:
    """Ingest one file end-to-end.

    Returns a small dict so the API layer can tell the user *which* backend
    actually parsed the file. This matters on Windows where Docling's
    optional torch-based components raise WinError 1114 at import time;
    we silently fall back to pdfplumber and report it instead of bubbling
    a long stack trace into the user's toast.
    """
    settings = get_settings()
    collection = collection or settings.chroma_collection
    store = ChromaStore(collection=collection)

    backend_used = "docling"
    fallback_reason: str | None = None
    with STAGE_LATENCY.labels(stage="extract").time():
        try:
            doc, backend_used, fallback_reason = await extract_with_backend(path)
        except Exception as e:  # noqa: BLE001 — never let ingest crash on extractor failure
            # Surface the failure cleanly to the caller rather than a 500.
            log.error("ingest_extract_failed", error=str(e)[:200])
            INGEST_DOCUMENTS.labels(
                source_type=path.suffix.lower(), outcome="extract_failed"
            ).inc()
            return {
                "chunks": 0,
                "backend": "none",
                "fallback_reason": "extract_failed",
                "error": str(e)[:200],
            }

    figure_text = "\n".join(f"[figure] {d}" for d in doc.figure_descriptions)
    full_text = (doc.text + "\n\n" + figure_text).strip() if figure_text else doc.text
    if not full_text.strip():
        INGEST_DOCUMENTS.labels(source_type=path.suffix.lower(), outcome="empty").inc()
        return {
            "chunks": 0,
            "backend": backend_used,
            "fallback_reason": fallback_reason,
        }

    with STAGE_LATENCY.labels(stage="chunk").time():
        chunks = chunk_text(full_text, chunk_size=800, overlap=120)

    if not chunks:
        INGEST_DOCUMENTS.labels(source_type=path.suffix.lower(), outcome="empty").inc()
        return {
            "chunks": 0,
            "backend": backend_used,
            "fallback_reason": fallback_reason,
        }

    prefix = doc_id_prefix or path.stem
    metadatas = [
        {
            "source": str(path),
            "chunk_index": i,
            "content_type": "chunk",
            "ocr_pages": doc.ocr_pages,
        }
        for i, _ in enumerate(chunks)
    ]
    ids = [f"{prefix}::chunk::{i}" for i in range(len(chunks))]
    texts = [c.text for c in chunks]

    with STAGE_LATENCY.labels(stage="embed_store").time():
        await store.add_texts(texts=texts, metadatas=metadatas, ids=ids)

    INGEST_DOCUMENTS.labels(source_type=path.suffix.lower(), outcome="ok").inc()
    log.info(
        "ingest_complete",
        source=str(path),
        chunks=len(chunks),
        backend=backend_used,
    )
    return {
        "chunks": len(chunks),
        "backend": backend_used,
        "fallback_reason": fallback_reason,
    }


async def ingest_directory(dir_path: Path) -> int:
    """Ingest every supported file in a directory."""
    paths: list[Path] = []
    for ext in ("*.pdf", "*.txt", "*.md"):
        paths.extend(dir_path.glob(ext))
    total = 0
    for p in paths:
        total += await ingest_file(p)
    # Rebuild BM25 after a directory pass.
    BM25Index.rebuild()
    return total


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(ingest_directory(Path("data")))