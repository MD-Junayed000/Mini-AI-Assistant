"""Smoke test for the gate evaluator's calibration intent.

We don't have live embeddings in tests — this just ensures the gate
math is monotonic and respects the configured threshold.
"""
from backend.config import get_settings
from backend.retrieval.gate import evaluate, GateVerdict
from backend.retrieval.hybrid import Retrieved


def _doc(rerank: float, dense: float, bm25: float) -> Retrieved:
    return Retrieved(
        id="x", text="x", metadata={}, rrf_score=0.0,
        rerank_score=rerank, dense_score=dense, bm25_score=bm25,
    )


def test_high_rerank_passes_gate():
    verdict = evaluate([_doc(0.85, 0.7, 4.0)])
    assert verdict.is_sufficient
    assert verdict.decision == "grounded"


def test_low_rerank_blocks_gate():
    verdict = evaluate([_doc(0.10, 0.1, 0.5)])
    assert not verdict.is_sufficient
    assert verdict.decision == "fallback"


def test_empty_retrieval_falls_back():
    verdict = evaluate([])
    assert not verdict.is_sufficient


def test_threshold_driveability():
    s = get_settings()
    s.confidence_gate_threshold = 0.99  # ridiculously strict
    verdict = evaluate([_doc(0.85, 0.7, 4.0)])
    assert not verdict.is_sufficient
    # Reset.
    s.confidence_gate_threshold = 0.62
