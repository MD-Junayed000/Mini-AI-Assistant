"""Migrate the on-disk Chroma KB to Chroma Cloud.

Reads every (id, document, metadata) triple from the local persistent
collection, then upserts them into the configured Chroma Cloud
database. Both sides bind the SAME embedding function (whatever is set
in ``HF_EMBEDDING_MODEL`` — default ``BAAI/bge-small-en-v1.5``, 384-d)
so the vector space is identical and existing chunk IDs stay stable.

Important: only run this script when the local store was ingested with
the SAME embedder as your .env currently names. If you change the model
in between, re-ingest from the source documents instead — mixing
embedding models in one collection silently breaks retrieval.

Usage:
    # 1. Make sure .env has CHROMA_USE_CLOUD=true and the cloud creds.
    # 2. Run with the LOCAL store pointed at your on-disk data:
    CHROMA_USE_CLOUD=false python scripts/migrate_to_chroma_cloud.py

The script is idempotent — chunk IDs are deterministic
(`{stem}::chunk::{i}`) so re-running is safe; Chroma's `upsert` will
replace existing rows in place.

After it finishes successfully, switch `CHROMA_USE_CLOUD=true` in your
environment and restart the API. The cloud collection will be the new
source of truth.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Force LOCAL mode for the read side, regardless of the user's .env.
os.environ["CHROMA_USE_CLOUD"] = "false"

from backend.config import get_settings  # noqa: E402
from backend.vector_store.chroma_store import ChromaStore  # noqa: E402


def _read_local() -> tuple[list[str], list[str], list[dict]]:
    """Stream every (id, doc, metadata) from the local collection."""
    # Re-import with cloud forced OFF so we definitely read from disk.
    s = get_settings()
    s.chroma_use_cloud = False  # mutate the cached instance
    local = ChromaStore()

    def _get() -> dict:
        return local._collection.get(include=["documents", "metadatas"])  # noqa: SLF001

    data = _get()
    ids: list[str] = list(data.get("ids") or [])
    docs: list[str] = list(data.get("documents") or [])
    metas: list[dict] = [m or {} for m in (data.get("metadatas") or [])]
    return ids, docs, metas


def _write_cloud(ids: list[str], docs: list[str], metas: list[dict]) -> int:
    """Upsert the triples into the cloud collection."""
    # Now flip to cloud mode and build a fresh client.
    s = get_settings()
    s.chroma_use_cloud = True
    if not s.chroma_api_key or not s.chroma_tenant:
        raise SystemExit(
            "CHROMA_API_KEY and CHROMA_TENANT must be set in .env before "
            "running this migration."
        )
    cloud = ChromaStore()

    BATCH = 256
    written = 0
    for i in range(0, len(ids), BATCH):
        cloud._collection.upsert(  # noqa: SLF001
            ids=ids[i:i + BATCH],
            documents=docs[i:i + BATCH],
            metadatas=metas[i:i + BATCH],
        )
        written += len(ids[i:i + BATCH])
    return written


async def main() -> None:
    print("Reading from local persistent store...")
    ids, docs, metas = _read_local()
    print(f"  found {len(ids)} chunk(s)")

    if not ids:
        print("Nothing to migrate — local collection is empty.")
        return

    print("Writing to Chroma Cloud...")
    written = _write_cloud(ids, docs, metas)
    print(f"  upserted {written} chunk(s)")
    print("Done. Set CHROMA_USE_CLOUD=true in .env and restart the API.")


if __name__ == "__main__":
    asyncio.run(main())