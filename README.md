# Mini AI Assistant 

Knowledge-grounded, tool-using assistant with hybrid retrieval, per-session
memory, and production-grade observability. Built for the take-home
assignment — no LangChain, no LangSmith.

## Stack

| Layer | Choice | Why |
|------|--------|-----|
| LLM (chat) | Ollama Cloud `qwen3.5:122b-cloud` (fallback `gpt-oss:120b-cloud`) | Free tier, native tool-calling, 256K context |
| Embeddings | HF Inference `BAAI/bge-small-en-v1.5` | Free tier, 384-d normalized cosine |
| Reranker | HF Inference `BAAI/bge-reranker-base` | Cross-encoder, reliably +0.05-0.10 nDCG |
| Vector DB | ChromaDB (persistent, local) | On-disk, single source of truth |
| BM25 | `rank_bm25` + pickle cache | Hybrid retrieval baseline |
| Parse | Docling (native) → RapidOCR (fallback) → HF Granite-Docling (figures only) | Staged, VLM only on figures |
| Memory | MongoDB Atlas free M0 (motor async) — falls back to in-process dict if unreachable | Doc-shaped + free |
| Backend | FastAPI + asyncio + `tenacity` | Plain Python, no LangChain |
| UI | Streamlit (sidebar + chat) | Demo-simple |

## Run

```bash
pip install -r requirements.txt
cp .env.example .env  # then fill keys
python -c "import asyncio; from pathlib import Path; from backend.ingestion.pipeline import ingest_directory; asyncio.run(ingest_directory(Path('data')))"
uvicorn main:app --reload --port 8000
streamlit run ui/streamlit_app.py
```

## API surface

- `POST /ingest` — multipart upload (PDF/TXT/MD)
- `POST /chat` — `{session_id, message}` → `{answer, sources, tool_calls, evidence, injection_risk, fallback_used}`
- `POST /session/{id}/reset`
- `GET  /healthz` — cached 10s
- `GET  /metrics` — Prometheus exposition
- `POST /admin/cache/refresh`

## Tool calling

The LLM emits JSON intents; the router dispatches:

```json
{"tool": "order_status", "args": {"order_id": "A1001"}}
{"tool": "product_search", "args": {"query": "wireless mouse", "top_k": 5}}
```

## Observability

- **Metrics**: Prometheus histograms per stage, answerability counters,
  tool-call outcomes, health gauge.
- **Logs**: JSON via `structlog`, PII-redacted, rotating 50MB × 5 files.
- **Errors**: Custom `AppError` hierarchy + `ERROR_MESSAGES` catalog; UI
  shows friendly banner with collapsible `detail`.
- **Health**: 10-second cached `/healthz` (per-component + overall).
- **Tracing**: optional OTel/OTLP — leave `OTEL_EXPORTER_OTLP_ENDPOINT`
  empty to disable.
- **Rate-limit**: per-session `slowapi` token bucket.
- **Injection defense**: heuristic detector + system-prompt hardening.

## Run-book

See `docs/runbook.md` for the on-call playbook — one section per
`ops/alerts.yaml` rule.
