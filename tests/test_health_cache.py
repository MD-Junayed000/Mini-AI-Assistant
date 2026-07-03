"""Item 5 — /healthz 10s cache."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from backend import observability
from backend.observability import health


@pytest.mark.asyncio
async def test_first_call_pings_dependencies():
    health._CACHE = None
    with (
        patch.object(health, "_probe_chroma", new=AsyncMock(return_value=("chroma", "up"))) as c,
        patch.object(health, "_probe_ollama", new=AsyncMock(return_value=("ollama", "up"))) as o,
        patch.object(health, "_probe_mongo", new=AsyncMock(return_value=("mongo", "up"))) as m,
    ):
        snap = await health.snapshot()
    assert snap.cached is False
    assert c.await_count == 1 and o.await_count == 1 and m.await_count == 1
    assert snap.overall == "up"


@pytest.mark.asyncio
async def test_second_call_within_ttl_is_cached():
    health._CACHE = None
    with (
        patch.object(health, "_probe_chroma", new=AsyncMock(return_value=("chroma", "up"))) as c,
        patch.object(health, "_probe_ollama", new=AsyncMock(return_value=("ollama", "up"))) as o,
        patch.object(health, "_probe_mongo", new=AsyncMock(return_value=("mongo", "up"))) as m,
    ):
        await health.snapshot()
        snap2 = await health.snapshot()
    assert snap2.cached is True
    assert c.await_count == 1 and o.await_count == 1 and m.await_count == 1


@pytest.mark.asyncio
async def test_cache_expires_after_ttl():
    health._CACHE = None
    with (
        patch.object(health, "_probe_chroma", new=AsyncMock(return_value=("chroma", "up"))) as c,
        patch.object(health, "_probe_ollama", new=AsyncMock(return_value=("ollama", "up"))) as o,
        patch.object(health, "_probe_mongo", new=AsyncMock(return_value=("mongo", "up"))) as m,
    ):
        await health.snapshot()
        # Force expiry by rewriting taken_at.
        assert health._CACHE is not None
        health._CACHE.taken_at -= 999
        snap3 = await health.snapshot()
    assert snap3.cached is False
    assert c.await_count == 2 and o.await_count == 2 and m.await_count == 2


@pytest.mark.asyncio
async def test_overall_degraded_when_one_down():
    health._CACHE = None
    with (
        patch.object(health, "_probe_chroma", new=AsyncMock(return_value=("chroma", "up"))),
        patch.object(health, "_probe_ollama", new=AsyncMock(return_value=("ollama", "down"))),
        patch.object(health, "_probe_mongo", new=AsyncMock(return_value=("mongo", "up"))),
    ):
        snap = await health.snapshot()
    assert snap.overall == "degraded"
    assert snap.components["ollama"] == "down"
