# Run-book — Mini AI Assistant (v2.2)

Each section corresponds to one rule in `ops/alerts.yaml`. Read the section
*before* going on-call.

## HighLatencyLLM

- **Symptom**: p99 of `request_stage_seconds{stage="llm"}` > 8s for 5m.
- **Likely causes**: Ollama Cloud degradation; under-sized Free-tier slot
  queuing; unusually long context flooded the GPU.
- **Triage**:
  1. Open Grafana → "p50 / p99 latency by stage" panel.
  2. Check Ollama Cloud status page.
  3. Inspect Mongo for sessions with abnormally long histories.
- **Mitigation**: lower `max_tokens` in `backend/llm/client.py`; switch
  primary to the fallback model; briefly widen the alert for the
  outage window.

## HighFallbackRate

- **Symptom**: `answerability_decisions_total{decision="fallback"} / total`
  > 30% for 10m.
- **Likely causes**: ingest drift (corpus changed but `confidentiality_gate`
  threshold wasn't recalibrated); embedding model swap; OCR errors on a
  new PDF batch.
- **Triage**:
  1. Re-run `tests/test_eval.py` against the current collection.
  2. Inspect `retrieval_topk_scores` distribution — if dense scores are
     flat, suspect embedding drift.
- **Mitigation**: re-ingest the affected corpus, recalibrate threshold,
  or tighten chunks.

## HighErrorRate

- **Symptom**: 5xx rate > 1% over 5m.
- **Triage**:
  1. Tail `logs/app.log` for `request_id` correlations.
  2. Check Ollama/HF/Mongo status dashboards.
- **Mitigation**: restart the FastAPI process; rotate `OLLAMA_CLOUD_API_KEY`
  if 401s are present.

## VectorStoreDown

- **Symptom**: Chroma scrape target down for 2m.
- **Triage**: `ls -la .chroma`; verify disk space; check that the
  process wasn't killed for OOM.
- **Mitigation**: clear `.chroma/` only if a full re-ingest is acceptable.

## HealthCheckDegraded

- **Symptom**: `health_status{component="..."} == 0` for 2m.
- **Triage**: open `/healthz` JSON, see which component.
- **Mitigation**: per-component.

## PromptInjectionSpike

- **Symptom**: `prompt_injection_total` rate > 0.5/s for 10m.
- **Triage**: grep logs for `"signals"` keys; identify the surface
  (`user` vs `document`).
- **Mitigation**: temporarily raise the detector threshold; flag the
  offending uploader.
