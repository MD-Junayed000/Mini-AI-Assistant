"""One-shot smoke test for the three session-end fixes.

Run with: python -m scripts.smoke_session_recovery
"""
from __future__ import annotations

import json
import sys

# 1. anaphoric retrieval
from backend.pipeline.chat import _build_retrieval_query, _is_anaphoric_followup

hist = [
    {"role": "user", "content": "who is junayed"},
    {
        "role": "assistant",
        "content": "Muhammad Junayed is from Chattogram, Bangladesh. He studies at CUET.",
    },
]
print("anaphoric('where he lives') =", _is_anaphoric_followup("where he lives"))
print(
    "augmented query =",
    repr(_build_retrieval_query("where he lives", hist, is_anaphoric=True)),
)
print(
    "plain query    =",
    repr(_build_retrieval_query("Hello there", hist, is_anaphoric=False)),
)

# 2. catalog dispatch + registry fall-through
from backend.tools.router import detect_intent
from backend.tools.registry import product_search

print()
print('detect("What products do we sell?") =', detect_intent("What products do we sell?"))
all_prods = product_search("", top_k=100)
print(f"product_search('', top_k=100) -> {len(all_prods)} products")
print("first 3 products =", json.dumps(all_prods[:3], indent=2))

# 3. order id with hash
print()
print('detect("Where is order #12345?") =', detect_intent("Where is order #12345?"))
print('detect("Where is order ORD-12345?") =', detect_intent("Where is order ORD-12345?"))

sys.exit(0)