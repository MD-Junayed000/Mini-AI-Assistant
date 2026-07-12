"""Session-registry regression tests."""
from __future__ import annotations

import asyncio

from backend.memory import Memory, Message


def test_touch_session_registers_empty_chat() -> None:
    mem = Memory()

    async def run() -> None:
        await mem.touch_session("session-abc")
        sessions = await mem.list_sessions()
        assert any(row["session_id"] == "session-abc" for row in sessions)
        row = next(row for row in sessions if row["session_id"] == "session-abc")
        assert row["turns"] == 0
        assert row["title"].startswith("session ")

    asyncio.run(run())


def test_append_keeps_session_visible() -> None:
    mem = Memory()

    async def run() -> None:
        await mem.touch_session("session-def")
        await mem.append(
            Message(session_id="session-def", role="user", content="hello", ts=123.0)
        )
        sessions = await mem.list_sessions()
        row = next(row for row in sessions if row["session_id"] == "session-def")
        assert row["turns"] == 1
        assert row["last_ts"] >= 123.0

    asyncio.run(run())