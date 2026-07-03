# Decisions (v2.2)

| ADR | Decision | Why |
|-----|----------|-----|
| 001 | Use Ollama Cloud for chat + HF Inference for embeddings | Cloud tier covers everything; HF handles the heavy-but-cheap embedding load |
| 002 | No LangChain; explicit JSON tool-intent router | Per the assignment constraint and to keep every routing decision visible |
| 003 | Staged PDF parse: Docling → RapidOCR → HF Granite-Docling (figures only) | Cheaper than full VLM scan; figure descriptions still earn their keep |
| 004 | Per-session `asyncio.Lock`; no global lock | Concurrent users must not block each other |
| 005 | `/healthz` is cached 10s | Free-tier Ollama charges per ping — naive monitoring is a budget leak |
| 006 | OpenTelemetry is opt-in | Default to zero cost; flip the env var to ship traces to Grafana Tempo |
| 007 | structlog redaction over a third-party formatter | Keeps the redactor in-repo so the rules can evolve with the codebase |
| 008 | Injection defense: detector + system-prompt hardening | Defense in depth; one alone is bypassable |
| 009 | MongoDB Atlas free M0 + in-process fallback | Demo-runnable without a cluster; production keeps the durable history |
| 010 | Rate limit per session, not per IP | Natural key for backend throttle; matches slowapi defaults |
