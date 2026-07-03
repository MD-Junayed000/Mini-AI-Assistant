"""Top-level ingestion: PDF → chunks → Chroma + BM25 + metric increments."""
from __future__ import annotations

import asyncio
from pathlib import Path

from backend.config import get_settings
from backend.ingestion.chunker import chunk_text
from backend.ingestion.docling_pipeline import extract
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
) -> int:
    """Ingest one file end-to-end. Returns the number of chunks stored."""
    settings = get_settings()
    collection = collection or settings.chroma_collection
    store = ChromaStore(collection=collection)

    with STAGE_LATENCY.labels(stage="extract").time():
        doc = await extract(path)

    figure_text = "\n".join(f"[figure] {d}" for d in doc.figure_descriptions)
    full_text = (doc.text + "\n\n" + figure_text).strip() if figure_text else doc.text
    if not full_text.strip():
        INGEST_DOCUMENTS.labels(source_type=path.suffix.lower(), outcome="empty").inc()
        return 0

    with STAGE_LATENCY.labels(stage="chunk").time():
        chunks = chunk_text(full_text, chunk_size=800, overlap=120)

    if not chunks:
        INGEST_DOCUMENTS.labels(source_type=path.suffix.lower(), outcome="empty").inc()
        return 0

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
    log.info("ingest_complete", source=str(path), chunks=len(chunks))
    return len(chunks)


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