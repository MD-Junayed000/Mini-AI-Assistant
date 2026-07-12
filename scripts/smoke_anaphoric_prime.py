"""Verify the anaphoric pipeline augmentation by manually priming the
module-level cache the same way a real request round-trip would.
"""
from __future__ import annotations

import sys

import backend.pipeline.chat as chat
from backend.pipeline.chat import _build_retrieval_query, _is_anaphoric_followup

# Simulate the end of a real turn where the assistant just answered.
chat._LAST_ASSISTANT_TURN[0] = (
    "Muhammad Junayed is from Chattogram, Bangladesh. He studies at CUET."
)
hist = [
    {"role": "user", "content": "who is junayed"},
    {"role": "assistant", "content": chat._LAST_ASSISTANT_TURN[0]},
]

print("is_anaphoric('where he lives') =", _is_anaphoric_followup("where he lives"))
print(
    "augmented query =",
    repr(_build_retrieval_query("where he lives", hist, is_anaphoric=True)),
)
print(
    "what are his publications =",
    repr(
        _build_retrieval_query(
            "what are his publications", hist, is_anaphoric=True
        )
    ),
)
print(
    "still no follow-up         =",
    repr(_build_retrieval_query("hello there", hist, is_anaphoric=False)),
)
sys.exit(0)