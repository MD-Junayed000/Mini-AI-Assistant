"""MongoDB-backed session memory.

Stores per-session message history keyed on session_id. Falls back
gracefully to an in-process list if Mongo is unreachable so unit tests
can run without a cluster.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import time
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
            "ts": self.ts or time.time(),
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
        self._session_coll_name = s.mongodb_collection + "_sessions"
        self._session_collection: Any = None
        self._meta_coll_name = s.mongodb_collection + "_meta"
        self._meta_collection: Any = None
        self._fallback: dict[str, list[dict[str, Any]]] = {}
        self._session_fallback: dict[str, dict[str, Any]] = {}
        # In-proc metadata cache so a Mongo cold-start still serves the
        # current rename in the few seconds before _ensure() resolves.
        self._meta_fallback: dict[str, dict[str, Any]] = {}
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
                self._session_collection = self._client[self._db][self._session_coll_name]
                self._meta_collection = self._client[self._db][self._meta_coll_name]
                self._healthy = True
            except Exception as e:  # noqa: BLE001
                log.warning("mongo_unavailable_using_memory_fallback", error=str(e))
                self._healthy = False

    def _touch_fallback_session(self, session_id: str, *, ts: float | None = None, title: str | None = None) -> None:
        now = float(ts or time.time())
        entry = self._session_fallback.setdefault(
            session_id,
            {
                "session_id": session_id,
                "created_ts": now,
                "last_ts": now,
            },
        )
        entry["last_ts"] = max(float(entry.get("last_ts", now)), now)
        entry.setdefault("created_ts", now)
        if title is not None:
            entry["title"] = title

    async def touch_session(self, session_id: str, *, ts: float | None = None, title: str | None = None) -> None:
        """Register a session even before the first message is sent."""
        if not session_id:
            return
        now = float(ts or time.time())
        self._touch_fallback_session(session_id, ts=now, title=title)
        await self._ensure()
        if self._healthy and self._session_collection is not None:
            try:
                update: dict[str, Any] = {
                    "$set": {"session_id": session_id, "last_ts": now},
                    "$setOnInsert": {"session_id": session_id, "created_ts": now},
                }
                if title is not None:
                    update["$set"]["title"] = title
                await self._session_collection.update_one(
                    {"session_id": session_id},
                    update,
                    upsert=True,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("mongo_session_touch_failed_falling_back", error=str(e))
                self._healthy = False

    async def append(self, m: Message) -> None:
        await self._ensure()
        if self._healthy and self._collection is not None:
            try:
                await self._collection.insert_one(m.to_doc())
                await self.touch_session(m.session_id, ts=m.ts)
                return
            except Exception as e:  # noqa: BLE001
                log.warning("mongo_write_failed_falling_back", error=str(e))
                self._healthy = False
        # In-memory fallback.
        doc = m.to_doc()
        self._fallback.setdefault(m.session_id, []).append(doc)
        self._touch_fallback_session(m.session_id, ts=doc["ts"])

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
                if self._session_collection is not None:
                    await self._session_collection.delete_many({"session_id": session_id})
                return
            except Exception as e:  # noqa: BLE001
                log.warning("mongo_reset_failed", error=str(e))
                self._healthy = False
        self._fallback[session_id] = []
        self._session_fallback.pop(session_id, None)
        self._meta_fallback.pop(session_id, None)

    async def rename_session(self, session_id: str, title: str) -> None:
        """Persist a user-set title for a session.

        Stored in a sidecar metadata collection so it survives uvicorn
        restarts. Falls back to the in-process cache when Mongo is cold.
        """
        v = (title or "").strip()
        if not v or not session_id:
            return
        # Always update the in-proc cache first so the next read sees the
        # new title regardless of Mongo state.
        self._meta_fallback[session_id] = {
            "session_id": session_id,
            "title": v,
        }
        self._touch_fallback_session(session_id, title=v)
        await self._ensure()
        if self._healthy and self._meta_collection is not None:
            try:
                await self._meta_collection.update_one(
                    {"session_id": session_id},
                    {"$set": {"session_id": session_id, "title": v}},
                    upsert=True,
                )
                if self._session_collection is not None:
                    await self._session_collection.update_one(
                        {"session_id": session_id},
                        {
                            "$set": {"session_id": session_id, "title": v, "last_ts": time.time()},
                            "$setOnInsert": {"session_id": session_id, "created_ts": time.time()},
                        },
                        upsert=True,
                    )
            except Exception as e:  # noqa: BLE001
                log.warning("mongo_rename_failed_keeping_in_memory", error=str(e))
                self._healthy = False

    async def delete_session_meta(self, session_id: str) -> None:
        """Drop any stored title for a session when it's deleted."""
        self._meta_fallback.pop(session_id, None)
        self._session_fallback.pop(session_id, None)
        await self._ensure()
        if self._healthy and self._meta_collection is not None:
            try:
                await self._meta_collection.delete_many({"session_id": session_id})
                if self._session_collection is not None:
                    await self._session_collection.delete_many({"session_id": session_id})
            except Exception as e:  # noqa: BLE001
                log.warning("mongo_meta_delete_failed", error=str(e))
                self._healthy = False

    async def get_session_title(self, session_id: str) -> str | None:
        """Return a persisted title (if any) for a session."""
        cached = self._meta_fallback.get(session_id)
        if cached and cached.get("title"):
            return cached["title"]
        cached = self._session_fallback.get(session_id)
        if cached and cached.get("title"):
            return cached["title"]
        await self._ensure()
        if self._healthy and self._meta_collection is not None:
            try:
                if self._session_collection is not None:
                    doc = await self._session_collection.find_one({"session_id": session_id})
                    if doc and doc.get("title"):
                        self._session_fallback[session_id] = {
                            "session_id": session_id,
                            "title": doc["title"],
                            "created_ts": float(doc.get("created_ts", 0.0) or 0.0),
                            "last_ts": float(doc.get("last_ts", 0.0) or 0.0),
                        }
                        return doc["title"]
                doc = await self._meta_collection.find_one({"session_id": session_id})
                if doc and doc.get("title"):
                    # Backfill the cache so subsequent reads are fast.
                    self._meta_fallback[session_id] = {
                        "session_id": session_id,
                        "title": doc["title"],
                    }
                    return doc["title"]
            except Exception as e:  # noqa: BLE001
                log.warning("mongo_title_lookup_failed", error=str(e))
                self._healthy = False
        return None

    async def list_sessions(self) -> list[dict[str, Any]]:
        """Return one row per known session_id with title, turn count, and last_ts.

        Title is derived from the first user message (trimmed to 60 chars) so
        the UI can show readable chat names. Used by the sidebar's session
        list.
        """
        await self._ensure()
        if self._healthy and self._collection is not None:
            try:
                pipeline: list[dict[str, Any]] = [
                    {"$sort": {"ts": 1}},
                    {
                        "$group": {
                            "_id": "$session_id",
                            "count": {"$sum": 1},
                            "last_ts": {"$max": "$ts"},
                            "first_user": {
                                "$first": {
                                    "$cond": [
                                        {"$eq": ["$role", "user"]},
                                        "$content",
                                        "",
                                    ]
                                }
                            },
                        }
                    },
                ]
                out: dict[str, dict[str, Any]] = {}
                async for doc in self._collection.aggregate(pipeline):
                    sid = doc["_id"]
                    raw = (doc.get("first_user") or "").strip().replace("\n", " ")
                    out[sid] = {
                        "session_id": sid,
                        "title": raw[:60] or f"session {sid[:8]}",
                        "turns": doc.get("count", 0),
                        "last_ts": float(doc.get("last_ts", 0.0) or 0.0),
                    }
                if self._session_collection is not None:
                    async for doc in self._session_collection.find({}):
                        sid = doc.get("session_id")
                        if not sid:
                            continue
                        existing = out.get(
                            sid,
                            {
                                "session_id": sid,
                                "title": f"session {sid[:8]}",
                                "turns": 0,
                                "last_ts": 0.0,
                            },
                        )
                        if doc.get("title"):
                            existing["title"] = doc["title"]
                        existing["last_ts"] = max(
                            float(existing.get("last_ts", 0.0) or 0.0),
                            float(doc.get("last_ts", 0.0) or 0.0),
                            float(doc.get("created_ts", 0.0) or 0.0),
                        )
                        out[sid] = existing
                if self._meta_collection is not None:
                    async for doc in self._meta_collection.find({}):
                        sid = doc.get("session_id")
                        title = doc.get("title")
                        if not sid or not title:
                            continue
                        existing = out.get(sid)
                        if existing is None:
                            out[sid] = {
                                "session_id": sid,
                                "title": title,
                                "turns": 0,
                                "last_ts": 0.0,
                            }
                        else:
                            existing["title"] = title
                rows = list(out.values())
                rows.sort(key=lambda r: r["last_ts"], reverse=True)
                return rows
            except Exception as e:  # noqa: BLE001
                log.warning("mongo_list_failed_falling_back", error=str(e))
                self._healthy = False
        # In-memory fallback: derive the same shape from the dict.
        out: dict[str, dict[str, Any]] = {}
        for sid, msgs in self._fallback.items():
            persisted = self._meta_fallback.get(sid, {}).get("title") or self._session_fallback.get(sid, {}).get("title")
            if persisted:
                title = persisted
            else:
                first_user = next(
                    (m.get("content", "") for m in msgs if m.get("role") == "user"),
                    "",
                )
                title = (first_user.strip() or f"session {sid[:8]}")[:60]
            out[sid] = {
                "session_id": sid,
                "title": title,
                "turns": len(msgs),
                "last_ts": float(max((m.get("ts", 0.0) for m in msgs), default=0.0)),
            }
        for sid, data in self._session_fallback.items():
            existing = out.get(
                sid,
                {
                    "session_id": sid,
                    "title": data.get("title") or f"session {sid[:8]}",
                    "turns": 0,
                    "last_ts": 0.0,
                },
            )
            if data.get("title"):
                existing["title"] = data["title"]
            existing["last_ts"] = max(float(existing.get("last_ts", 0.0) or 0.0), float(data.get("last_ts", 0.0) or 0.0))
            out[sid] = existing
        rows = list(out.values())
        rows.sort(key=lambda r: r["last_ts"], reverse=True)
        return rows

    async def delete_session(self, session_id: str) -> bool:
        """Forget a session entirely (history + memory). Returns True if anything was removed."""
        await self._ensure()
        # Always wipe the meta cache too so a re-created chat with the same
        # id doesn't inherit the previous title.
        self._meta_fallback.pop(session_id, None)
        removed = False
        if self._healthy and self._collection is not None:
            try:
                res = await self._collection.delete_many({"session_id": session_id})
                removed = bool(getattr(res, "deleted_count", 0))
                if self._meta_collection is not None:
                    try:
                        await self._meta_collection.delete_many({"session_id": session_id})
                    except Exception:  # noqa: BLE001
                        pass
                if self._session_collection is not None:
                    try:
                        await self._session_collection.delete_many({"session_id": session_id})
                    except Exception:  # noqa: BLE001
                        pass
                return removed
            except Exception as e:  # noqa: BLE001
                log.warning("mongo_delete_failed_falling_back", error=str(e))
                self._healthy = False
        if session_id in self._fallback:
            self._fallback.pop(session_id)
            removed = True
        self._session_fallback.pop(session_id, None)
        self._meta_fallback.pop(session_id, None)
        return removed

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._collection = None
            self._session_collection = None
            self._meta_collection = None
            self._healthy = False