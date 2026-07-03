"""Tool registry + router."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.tools import registry, router
from backend.tools.router import parse_tool_intent


def _patch_data(tmp_path: Path, monkeypatch):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "orders.json").write_text(
        json.dumps([
            {"order_id": "B1", "customer": "a", "status": "shipped",
             "eta_days": 1, "total_usd": 9.99, "items": []}
        ]),
        encoding="utf-8",
    )
    (tmp_path / "data" / "products.json").write_text(
        json.dumps([
            {"sku": "S1", "name": "Test Keyboard",
             "category": "peripherals", "price_usd": 99.0, "stock": 1, "tags": ["x"]}
        ]),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    registry.refresh_cache()


def test_parse_tool_intent_json_fence():
    text = 'Here you go:\n```json\n{"tool": "order_status", "args": {"order_id": "A1001"}}\n```'
    call = parse_tool_intent(text)
    assert call is not None
    assert call.name == "order_status"
    assert call.args["order_id"] == "A1001"


def test_parse_tool_intent_bare_object():
    text = 'The tool call: {"tool":"product_search","args":{"query":"mouse","top_k":3}}'
    call = parse_tool_intent(text)
    assert call is not None
    assert call.name == "product_search"
    assert call.args["top_k"] == 3


def test_parse_returns_none_when_no_json():
    assert parse_tool_intent("Just a normal sentence.") is None


def test_parse_raises_on_missing_required_arg():
    from backend.errors import ValidationError

    with pytest.raises(ValidationError):
        parse_tool_intent('{"tool": "order_status", "args": {}}')


def test_dispatch_order_status(tmp_path, monkeypatch):
    _patch_data(tmp_path, monkeypatch)
    result = router.dispatch(router.ToolCall(name="order_status", args={"order_id": "B1"}))
    assert result["status"] == "shipped"


def test_dispatch_product_search(tmp_path, monkeypatch):
    _patch_data(tmp_path, monkeypatch)
    result = router.dispatch(router.ToolCall(name="product_search", args={"query": "keyboard"}))
    assert isinstance(result, list)
    assert result[0]["sku"] == "S1"


def test_dispatch_unknown_tool():
    from backend.errors import ToolError

    with pytest.raises(ToolError):
        router.dispatch(router.ToolCall(name="magic", args={}))
