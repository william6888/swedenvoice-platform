"""Tester för draft_order → place_order och Vapi tool-extraktion."""

from __future__ import annotations

import json
import time

import pytest

import confirmation
import main as M
from tests.fake_supabase import FakeSupabase


@pytest.fixture(autouse=True)
def _reset_main(tmp_path, monkeypatch):
    db = FakeSupabase()
    monkeypatch.setattr(M, "_supabase_client", db)
    monkeypatch.setattr(M, "ORDER_REQUIRE_DB_COMMIT", True)
    monkeypatch.setattr(M, "RESTAURANT_UUID", "u-rest-1")
    monkeypatch.setenv("DRAFT_SIGNING_SECRET", "test-draft-secret-for-hmac-signing-32b")
    orders_file = tmp_path / "orders.json"
    monkeypatch.setattr(M, "ORDERS_FILE", orders_file)
    M.save_orders([])
    M._CALL_DRAFT_CACHE.clear()
    yield db


def _items_payload():
    return {
        "items": [{"id": 1, "name": "Capricciosa", "quantity": 1}],
        "special_requests": "",
    }


def test_extract_vapi_tool_calls_draft_and_place():
    msg = {
        "toolCallList": [
            {
                "id": "tc-draft",
                "function": {
                    "name": "draft_order",
                    "arguments": json.dumps(_items_payload()),
                },
            },
            {
                "id": "tc-place",
                "function": {
                    "name": "place_order",
                    "arguments": json.dumps(_items_payload()),
                },
            },
        ],
    }
    calls = M._extract_vapi_tool_calls(msg)
    assert len(calls) == 2
    assert calls[0][1] == "draft_order"
    assert calls[1][1] == "place_order"


def test_draft_order_params_returns_readback(monkeypatch):
    monkeypatch.setattr(M, "REQUIRE_DRAFT_TOKEN", False)
    body = {"message": {"call": {"id": "call-draft-1"}}}
    result = M._handle_draft_order_params(
        _items_payload(),
        body,
        None,
        "Gislegrillen_01",
        "Gislegrillen_01",
        "u-rest-1",
        tool_call_id="tc-1",
    )
    assert result["name"] == "draft_order"
    payload = json.loads(result["result"])
    assert payload["success"] is True
    assert "Capricciosa" in payload["readback"]
    assert "draft_token" not in payload
    assert "kr" not in payload["readback"]
    cached = M._get_cached_draft_for_call("call-draft-1")
    assert cached is not None
    assert cached.get("draft_token")


def test_place_order_uses_cached_draft_token_when_required(monkeypatch, _reset_main):
    monkeypatch.setattr(M, "REQUIRE_DRAFT_TOKEN", True)
    body = {"message": {"call": {"id": "call-cache-1"}}}
    draft_res = M._handle_draft_order_params(
        _items_payload(),
        body,
        None,
        "Gislegrillen_01",
        "Gislegrillen_01",
        "u-rest-1",
    )
    draft_payload = json.loads(draft_res["result"])
    assert draft_payload["success"]

    # place_order utan draft_token i params – ska hämta från cache
    place_res = M._handle_place_order_params(
        _items_payload(),
        body,
        None,
        "Gislegrillen_01",
        "Gislegrillen_01",
        "u-rest-1",
        tool_call_id="tool-place-1",
    )
    place_payload = json.loads(place_res["result"])
    assert place_payload.get("success") is True
    assert place_payload.get("order_id")


def test_place_order_auto_drafts_when_no_prior_draft(monkeypatch, _reset_main):
    """AI skippar draft_order – order ska ändå gå igenom (auto-draft)."""
    monkeypatch.setattr(M, "REQUIRE_DRAFT_TOKEN", True)
    body = {"message": {"call": {"id": "call-nodraft"}}}
    place_res = M._handle_place_order_params(
        _items_payload(),
        body,
        None,
        "Gislegrillen_01",
        "Gislegrillen_01",
        "u-rest-1",
        tool_call_id="tool-only",
    )
    place_payload = json.loads(place_res["result"])
    assert place_payload.get("success") is True
    assert place_payload.get("order_id")


def test_draft_then_place_clears_cache(monkeypatch, _reset_main):
    monkeypatch.setattr(M, "REQUIRE_DRAFT_TOKEN", True)
    body = {"message": {"call": {"id": "call-full"}}}
    M._handle_draft_order_params(
        _items_payload(),
        body,
        None,
        "Gislegrillen_01",
        "Gislegrillen_01",
        "u-rest-1",
    )
    assert M._get_cached_draft_for_call("call-full") is not None
    place_res = M._handle_place_order_params(
        _items_payload(),
        body,
        None,
        "Gislegrillen_01",
        "Gislegrillen_01",
        "u-rest-1",
        tool_call_id="tool-1",
    )
    assert json.loads(place_res["result"])["success"] is True
    assert M._get_cached_draft_for_call("call-full") is None
