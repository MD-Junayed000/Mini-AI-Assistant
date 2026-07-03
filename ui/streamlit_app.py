"""Streamlit UI — sidebar + chat + friendly error banner.

Run with: streamlit run ui/streamlit_app.py
"""
from __future__ import annotations

import uuid

import httpx
import streamlit as st

st.set_page_config(page_title="Mini AI Assistant", page_icon="🤖", layout="wide")

API = "http://localhost:8000"


def _session_id() -> str:
    return st.session_state.setdefault("session_id", uuid.uuid4().hex[:12])


# ----- Sidebar ------------------------------------------------------------
with st.sidebar:
    st.title("📚 Knowledge Base")
    uploaded = st.file_uploader("Upload a document (PDF / TXT / MD)", type=["pdf", "txt", "md"])
    if uploaded and st.button("Ingest"):
        try:
            with httpx.Client(timeout=120) as cx:
                r = cx.post(f"{API}/ingest", files={"file": (uploaded.name, uploaded.getvalue())})
                r.raise_for_status()
                st.success(f"Ingested {r.json().get('chunks', 0)} chunks.")
        except httpx.HTTPError as e:
            st.error(e)

    st.divider()
    if st.button("Clear conversation"):
        sid = _session_id()
        try:
            httpx.post(f"{API}/session/{sid}/reset").raise_for_status()
            st.session_state.messages = []
            st.experimental_rerun()
        except httpx.HTTPError as e:
            st.error(e)

# ----- Main chat ----------------------------------------------------------
st.title("🤖 Mini AI Assistant")

sid = _session_id()
st.caption(f"Session: `{sid}`")

messages: list[dict] = st.session_state.setdefault("messages", [])

for m in messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("sources"):
            with st.expander(f"Sources ({len(m['sources'])})"):
                for s in m["sources"]:
                    st.markdown(f"- **{s['id']}** — {s.get('preview', '')[:160]}…")

user_input = st.chat_input("Ask anything about orders, products, or the knowledge base…")
if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)
    messages.append({"role": "user", "content": user_input})

    with st.chat_message("assistant"):
        placeholder = st.empty()
        try:
            with httpx.Client(timeout=120) as cx:
                r = cx.post(
                    f"{API}/chat",
                    json={"session_id": sid, "message": user_input},
                )
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPStatusError as e:
            try:
                data = e.response.json()
            except Exception:  # noqa: BLE001
                data = {"error": str(e), "code": "internal_error"}
            placeholder.error(data.get("friendly", "Something went wrong."))
            with st.expander("Details"):
                st.json(data)
            messages.append({"role": "assistant", "content": data.get("friendly", "Error.")})
        except httpx.HTTPError as e:
            placeholder.error(f"Network error: {e}")
            messages.append({"role": "assistant", "content": "Network error."})
        else:
            placeholder.markdown(data.get("answer", ""))
            sources = data.get("sources") or []
            if sources:
                with st.expander(f"Sources ({len(sources)})"):
                    for s in sources:
                        st.markdown(f"- **{s['id']}** — {s.get('preview', '')[:160]}…")
            msgs_text = data.get("answer", "")
            messages.append({"role": "assistant", "content": msgs_text, "sources": sources})

st.session_state.messages = messages