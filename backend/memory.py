"""MongoDB-backed session memory.

Stores per-session message history keyed on session_id. Falls back
gracefully to an in-process list if Mongo is unreachable so unit tests
can run without a cluster.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.config import get_settings
from backend.errors import MemoryError_
from backend.observability.logging_config import get_logger

log = get_logger("memory")


@dataclass
class Message:
    session_id: str
    role: str
    content: str
    metadata: dict[str, Any] | None = None
    ts: float = 0.0

    def to_doc(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata or {},
            "ts": self.ts or asyncio.get_event_loop().time(),
        }


class Memory:
    """Async session memory with optional Mongo backing."""

    def __init__(self) -> None:
        s = get_settings()
        self._uri = s.mongodb_uri
        self._db = s.mongodb_db
        self._coll = s.mongodb_collection
        self._client: Any = None
        self._collection: Any = None
        self._fallback: dict[str, list[dict[str, Any]]] = {}
        self._init_lock = asyncio.Lock()
        self._healthy = False

    async def _ensure(self) -> None:
        if self._collection is not None and self._healthy:
            return
        async with self._init_lock:
            if self._collection is not None and self._healthy:
                return
            try:
                from motor.motor_asyncio import AsyncIOMotorClient

                self._client = AsyncIOMotorClient(self._uri, serverSelectionTimeoutMS=2000)
                # Ping
                await self._client.admin.command("ping")
                self._collection = self._client[self._db][self._coll]
                self._healthy = True
            except Exception as e:  # noqa: BLE001
                log.warning("mongo_unavailable_using_memory_fallback", error=str(e))
                self._healthy = False

    async def append(self, m: Message) -> None:
        await self._ensure()
        if self._healthy and self._collection is not None:
            try:
                await self._collection.insert_one(m.to_doc())
                return
            except Exception as e:  # noqa: BLE001
                log.warning("mongo_write_failed_falling_back", error=str(e))
                self._healthy = False
        # In-memory fallback.
        self._fallback.setdefault(m.session_id, []).append(m.to_doc())

    async def history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        await self._ensure()
        if self._healthy and self._collection is not None:
            try:
                cursor = (
                    self._collection.find({"session_id": session_id})
                    .sort("ts", 1)
                    .limit(limit)
                )
                out: list[dict[str, Any]] = []
                async for doc in cursor:
                    doc.pop("_id", None)
                    out.append(doc)
                return out
            except Exception as e:  # noqa: BLE001
                log.warning("mongo_read_failed_falling_back", error=str(e))
                self._healthy = False
        return list(self._fallback.get(session_id, [])[-limit:])

    async def reset(self, session_id: str) -> None:
        await self._ensure()
        if self._healthy and self._collection is not None:
            try:
                await self._collection.delete_many({"session_id": session_id})
                return
            except Exception as e:  # noqa: BLE001
                log.warning("mongo_reset_failed", error=str(e))
                self._healthy = False
        self._fallback[session_id] = []

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._collection = None
            self._healthy = False