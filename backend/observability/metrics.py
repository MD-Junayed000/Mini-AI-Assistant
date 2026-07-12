"""Prometheus metrics registry — used by the /metrics endpoint.

All histograms are per-stage so dashboards can split retrieval vs. llm vs.
tool latency. Counters are per-decision so we can compute fallback rates.
"""
from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry()

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests served, partitioned by method/path/status.",
    ["method", "endpoint", "status"],
    registry=REGISTRY,
)
HTTP_LATENCY = Histogram(
    "http_request_seconds",
    "End-to-end HTTP latency by endpoint.",
    ["method", "endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
    registry=REGISTRY,
)

STAGE_LATENCY = Histogram(
    "request_stage_seconds",
    "Per-stage latency. Use histogram_quantile() on this.",
    ["stage"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
    registry=REGISTRY,
)

ANSWERABILITY = Counter(
    "answerability_decisions_total",
    "Count of retrieval answers by decision: grounded | fallback | empty.",
    ["decision"],
    registry=REGISTRY,
)

TOOL_CALLS = Counter(
    "tool_calls_total",
    "Tool invocations by tool name and outcome.",
    ["tool", "outcome"],
    registry=REGISTRY,
)
TOOL_LATENCY = Histogram(
    "tool_call_seconds",
    "Tool execution latency by tool.",
    ["tool"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
    registry=REGISTRY,
)

RETRIEVAL_RESULTS = Histogram(
    "retrieval_topk_scores",
    "Top-k dense retrieval cosine scores by source.",
    ["source"],
    buckets=(0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
    registry=REGISTRY,
)
RERANK_TOP_SCORE = Histogram(
    "rerank_top_score",
    "Highest cross-encoder rerank score per request.",
    buckets=(0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
    registry=REGISTRY,
)

HEALTH_STATUS = Gauge(
    "health_status",
    "1 = up, 0 = down. One series per dependency component.",
    ["component"],
    registry=REGISTRY,
)

INGEST_DOCUMENTS = Counter(
    "ingest_documents_total",
    "Documents ingested by source type.",
    ["source_type", "outcome"],
    registry=REGISTRY,
)

PROMPT_INJECTION = Counter(
    "prompt_injection_total",
    "Detected prompt-injection signals across user input + uploaded docs.",
    ["surface"],  # user | document
    registry=REGISTRY,
)
RATE_LIMIT_HITS = Counter(
    "rate_limit_hits_total",
    "Number of requests rejected by the per-session rate limiter.",
    ["endpoint"],
    registry=REGISTRY,
)
