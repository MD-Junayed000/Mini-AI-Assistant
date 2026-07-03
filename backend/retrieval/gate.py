"""Multi-signal answerability gate.

The gate refuses to answer when evidence is too weak — replacing the
single-similarity-threshold anti-pattern with a more honest combination.

Signals:
  - rerank_top   : top rerank score
  - rerank_gap   : gap between top1 and top2 (small gap → ambiguous)
  - dense_top    : top dense cosine
  - bm25_top     : top BM25 (normalised to [0,1] via /5)
  - doc_count    : number of retrieved docs that survived fusion

Calibrated threshold lives in settings.confidence_gate_threshold.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.config import get_settings
from backend.observability.metrics import ANSWERABILITY
from backend.retrieval.hybrid import Retrieved


@dataclass
class GateVerdict:
    is_sufficient: bool
    signals: dict[str, float]
    decision: str  # "grounded" | "ambiguous" | "fallback"


def _score_to_unit(x: float | None) -> float:
    if x is None:
        return 0.0
    return max(0.0, min(1.0, float(x)))


def evaluate(retrieved: list[Retrieved]) -> GateVerdict:
    if not retrieved:
        ANSWERABILITY.labels(decision="empty").inc()
        return GateVerdict(False, {}, "fallback")

    rerank_top = _score_to_unit(retrieved[0].rerank_score)
    rerank_next = _score_to_unit(retrieved[1].rerank_score) if len(retrieved) > 1 else 0.0
    rerank_gap = max(0.0, rerank_top - rerank_next)
    dense_top = _score_to_unit(retrieved[0].dense_score)
    bm25_top = _score_to_unit((retrieved[0].bm25_score or 0.0) / 5.0)
    doc_count = float(len(retrieved))

    signals = {
        "rerank_top": rerank_top,
        "rerank_gap": rerank_gap,
        "dense_top": dense_top,
        "bm25_top": bm25_top,
        "doc_count": doc_count,
    }

    # Weighted blend. Weights chosen so rerank dominates because the
    # cross-encoder is the most reliable single signal.
    score = (
        0.50 * rerank_top
        + 0.20 * rerank_gap
        + 0.15 * dense_top
        + 0.10 * bm25_top
        + 0.05 * min(1.0, doc_count / 3.0)
    )

    threshold = get_settings().confidence_gate_threshold
    is_sufficient = score >= threshold

    decision = "grounded" if is_sufficient else "fallback"
    ANSWERABILITY.labels(decision=decision).inc()
    return GateVerdict(is_sufficient, signals, decision)
