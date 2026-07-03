"""Tool router — explicit JSON-intent dispatch.

We do NOT use LangChain or native OpenAI tool-calling; the LLM emits a
JSON object with {tool, args} and we dispatch here. The intent and args
are also validated before invocation.

Why this shape:
  - Works with any chat model (no dependency on tool-calling guarantees).
  - Easy to test in isolation.
  - Easy to observe — every dispatch produces a Prometheus increment and
    a structlog event.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from backend.errors import ToolError, ValidationError
from backend.observability.metrics import TOOL_CALLS, TOOL_LATENCY
from backend.tools.registry import order_status, product_search


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]


_TOOL_SCHEMA: dict[str, dict[str, Any]] = {
    "order_status": {
        "required": ["order_id"],
        "properties": {"order_id": {"type": "string"}},
    },
    "product_search": {
        "required": ["query"],
        "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}},
    },
}

# JSON fence extraction — looks for ```json ... ``` first, then { ... }.
_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_OBJ = re.compile(r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})", re.DOTALL)


def parse_tool_intent(text: str) -> ToolCall | None:
    """Extract a {tool, args} JSON intent from the LLM's response text.

    Returns None when the model did not request a tool. Raises
    ValidationError if a JSON object was emitted but it doesn't parse.
    """
    if not text:
        return None
    blob: str | None = None
    fence = _JSON_FENCE.search(text)
    if fence:
        blob = fence.group(1)
    else:
        obj = _JSON_OBJ.search(text)
        if obj:
            blob = obj.group(1)
    if blob is None:
        return None
    try:
        payload = json.loads(blob)
    except json.JSONDecodeError as e:
        raise ValidationError(f"tool_intent_unparseable: {e.msg}") from e

    name = payload.get("tool") or payload.get("name")
    args = payload.get("args") or payload.get("arguments") or {}
    if not isinstance(name, str) or not isinstance(args, dict):
        raise ValidationError("tool_intent_shape")
    if name not in _TOOL_SCHEMA:
        raise ValidationError(f"tool_unknown: {name}")
    schema = _TOOL_SCHEMA[name]
    for req in schema["required"]:
        if req not in args:
            raise ValidationError(f"tool_arg_missing: {req}")
    return ToolCall(name=name, args=args)


def dispatch(call: ToolCall) -> dict[str, Any]:
    """Run a tool call with metric + log side-effects."""
    with TOOL_LATENCY.labels(tool=call.name).time():
        try:
            if call.name == "order_status":
                result = order_status(call.args["order_id"])
            elif call.name == "product_search":
                result = product_search(
                    query=call.args["query"],
                    top_k=int(call.args.get("top_k", 5)),
                )
            else:
                raise ToolError(f"unhandled_tool: {call.name}")
        except ToolError:
            TOOL_CALLS.labels(tool=call.name, outcome="error").inc()
            raise
        except KeyError:
            TOOL_CALLS.labels(tool=call.name, outcome="not_found").inc()
            raise ToolError(f"not_found: {call.args.get('order_id', '?')}", tool=call.name)
        except Exception as e:  # noqa: BLE001
            TOOL_CALLS.labels(tool=call.name, outcome="error").inc()
            raise ToolError(str(e), tool=call.name) from e

    TOOL_CALLS.labels(tool=call.name, outcome="ok").inc()
    return result