"""Item 2 — per-session rate limit (over FastAPI TestClient)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from main import create_app, install_memory
    from backend.memory import Memory

    app = create_app()
    install_memory(Memory())
    return TestClient(app)


def test_session_buckets_independent(client):
    s1 = "session-one"
    s2 = "session-two"
    # Drain session one's bucket.
    for i in range(5):
        r = client.post("/chat", json={"session_id": s1, "message": f"hi {i}"})
        assert r.status_code in (200, 502, 503)  # not necessarily 200
    # Session two still has a full bucket.
    r2 = client.post("/chat", json={"session_id": s2, "message": "fresh"})
    assert r2.status_code != 429


def test_rate_limit_returns_429(client):
    sid = "flooder"
    last_status = None
    for i in range(20):
        r = client.post(
            "/chat",
            json={"session_id": sid, "message": "spam"},
        )
        last_status = r.status_code
        if r.status_code == 429:
            break
    assert last_status == 429


def test_retry_after_header_on_429(client):
    sid = "flooder-2"
    for i in range(20):
        r = client.post("/chat", json={"session_id": sid, "message": "go"})
        if r.status_code == 429:
            assert "Retry-After" in {k.title() for k in r.headers.keys()}
            break
    else:
        pytest.skip("did not reach 429 within 20 calls")
