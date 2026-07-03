"""Per-session locks — no global lock contention."""
from __future__ import annotations

import asyncio

from backend.locks import lock_count, session_lock


async def test_concurrent_sessions_dont_block():
    async def worker(sid: str, barrier: asyncio.Event):
        async with session_lock(sid):
            await barrier.wait()

    bar = asyncio.Event()
    t1 = asyncio.create_task(worker("a", bar))
    t2 = asyncio.create_task(worker("b", bar))
    # Both are now waiting on the barrier; both locks are held.
    await asyncio.sleep(0.05)
    # If we had a global lock, only one would be here.
    bar.set()
    await asyncio.gather(t1, t2)
    assert lock_count() == 2


async def test_same_session_serialised():
    order: list[str] = []

    async def worker(label: str):
        async with session_lock("same"):
            order.append(f"{label}:enter")
            await asyncio.sleep(0.02)
            order.append(f"{label}:exit")

    await asyncio.gather(worker("A"), worker("B"))
    # Strict ordering because of the lock.
    assert order[0] == "A:enter"
    assert order[1] == "A:exit"
    assert order[2] == "B:enter"
    assert order[3] == "B:exit"
