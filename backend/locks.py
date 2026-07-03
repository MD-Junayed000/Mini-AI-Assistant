"""Per-session asyncio.Lock dictionary.

v2.1 design: never a global lock — concurrent sessions must not block each
other. The dict is populated on demand; locks are reused on next call.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

_LOCKS: dict[str, asyncio.Lock] = {}
_DICT_LOCK = asyncio.Lock()


async def _get_lock(session_id: str) -> asyncio.Lock:
    async with _DICT_LOCK:
        lock = _LOCKS.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            _LOCKS[session_id] = lock
        return lock


@asynccontextmanager
async def session_lock(session_id: str) -> AsyncIterator[asyncio.Lock]:
    """Acquire the per-session lock, releasing in `finally`."""
    lock = await _get_lock(session_id)
    async with lock:
        yield lock


def lock_count() -> int:
    """For /metrics debugging only."""
    return len(_LOCKS)