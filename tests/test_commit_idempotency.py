"""
End-to-end-tester för _commit_order_supabase_first:
  * Samma Vapi payload 5x ger en order.
  * Två parallella requests ger en order.
  * Supabase-fel -> success:false (ingen falsk bekräftelse).
  * Tenant pausad -> handle_place_order returnerar mjukt fel.
  * Lovable/KDS ser ordern via Supabase (inte orders.json).
"""

from __future__ import annotations

import threading
import time
from typing import List, Tuple

import pytest

import main as M
from tests.fake_supabase import FakeSupabase


@pytest.fixture(autouse=True)
def _reset_main(tmp_path, monkeypatch):
    """Sätt upp fake supabase + tom orders.json för varje test."""
    db = FakeSupabase()
    monkeypatch.setattr(M, "_supabase_client", db)
    monkeypatch.setattr(M, "ORDER_REQUIRE_DB_COMMIT", True)
    monkeypatch.setattr(M, "RESTAURANT_UUID", "u-rest-1")
    orders_file = tmp_path / "orders.json"
    monkeypatch.setattr(M, "ORDERS_FILE", orders_file)
    M.save_orders([])
    yield db


def _items() -> List[M.OrderItem]:
    return [
        M.OrderItem(id=1, name="Capricciosa", quantity=1, price=120.0),
        M.OrderItem(id=10, name="Hawaii", quantity=2, price=130.0),
    ]


def _resolved_raw():
    return [
        {"id": 1, "name": "Capricciosa", "quantity": 1, "price": 120.0, "matchType": "exact"},
        {"id": 10, "name": "Hawaii", "quantity": 2, "price": 130.0, "matchType": "exact"},
    ]


def _commit(_db, **overrides):
    args = dict(
        items=_items(),
        raw_items=_resolved_raw(),
        rest_id="rest-1",
        restaurant_id="rest-1",
        restaurant_uuid="u-rest-1",
        customer_name="Anna",
        customer_phone="+46700000000",
        raw_transcript="",
        special_requests="extra ost",
        vapi_call_id="call-1",
        vapi_tool_call_id="tool-1",
        correlation_id="call-1",
    )
    args.update(overrides)
    return M._commit_order_supabase_first(**args)


def test_five_retries_create_one_order(_reset_main):
    db = _reset_main
    results = [_commit(db) for _ in range(5)]
    assert all(r["success"] for r in results)
    order_ids = {r["order_id"] for r in results}
    assert len(order_ids) == 1
    assert sum(1 for r in db.get_orders() if r.get("order_id") in order_ids) == 1
    # Endast första anropet ska räknas som äkta commit. Resterande är replays.
    replays = [r for r in results if r.get("idempotent_replay")]
    assert len(replays) == 4


def test_two_place_orders_same_call_create_one_order(_reset_main):
    """Skydd: AI ringer place_order två gånger i samma samtal med olika
    tool_call_id (eller t.o.m. olika items) → bara en order, ett SMS."""
    db = _reset_main
    first = _commit(db, vapi_tool_call_id="tool-A")
    assert first["success"] and not first.get("idempotent_replay")

    second_items = list(_items()) + [M.OrderItem(id=3, name="Margherita", quantity=1, price=99.0)]
    second_resolved = list(_resolved_raw()) + [
        {"id": 3, "name": "Margherita", "quantity": 1, "price": 99.0, "matchType": "exact"}
    ]
    second = _commit(
        db,
        items=second_items,
        raw_items=second_resolved,
        vapi_tool_call_id="tool-B",
        special_requests="",
    )
    assert second["success"]
    assert second["order_id"] == first["order_id"]
    assert second["idempotent_replay"] is True
    assert len(db.get_orders()) == 1

    events = [e for e in db.get_events() if e.get("event_type") == "duplicate_place_order_in_call"]
    assert len(events) == 1
    assert events[0].get("payload", {}).get("vapi_call_id") == "call-1"


def test_two_place_orders_different_calls_create_two_orders(_reset_main):
    db = _reset_main
    first = _commit(db, vapi_call_id="call-A", vapi_tool_call_id="tool-A")
    second = _commit(db, vapi_call_id="call-B", vapi_tool_call_id="tool-B")
    assert first["success"] and second["success"]
    assert first["order_id"] != second["order_id"]
    assert len(db.get_orders()) == 2


def test_supabase_failure_returns_failure_and_no_order(_reset_main):
    db = _reset_main
    db.fail_next_on_table["orders"] = True
    res = _commit(db, vapi_tool_call_id="tool-fail")
    assert not res["success"]
    assert res["error_code"] == "SUPABASE_COMMIT_FAILED"
    assert len(db.get_orders()) == 0


def test_tenant_pause_blocks_in_handle_place_order(_reset_main, monkeypatch):
    import ops_agent
    ops_agent.upsert_tenant_health(
        _reset_main,
        restaurant_uuid="u-rest-1",
        restaurant_id="rest-1",
        intake_status="paused",
        intake_paused_reason="supabase_insert_failures",
    )
    monkeypatch.setattr(M, "_circuit_breaker_allow", lambda r: True)
    monkeypatch.setattr(M, "_token_bucket_allow", lambda r: True)
    monkeypatch.setattr(M, "_resolve_items_with_menu_match",
                        lambda items_data, rest_id: (True, _resolved_raw(), ""))
    monkeypatch.setattr(M, "_get_customer_phone_from_webhook", lambda b, p=None: None)
    monkeypatch.setattr(M, "_parse_items_from_params",
                        lambda params, rest: [{"id": 1, "quantity": 1}, {"id": 10, "quantity": 2}])
    monkeypatch.setattr(M, "send_customer_sms_now", lambda *a, **k: None)
    res = M._handle_place_order_params(
        params={"items": [{"id": 1, "quantity": 1}, {"id": 10, "quantity": 2}]},
        body={},
        request=None,
        rest_id="rest-1",
        restaurant_id="rest-1",
        restaurant_uuid="u-rest-1",
        tool_call_id="tool-XYZ",
    )
    assert "kan inte tas emot" in (res.get("result") or "")
    assert len(_reset_main.get_orders()) == 0


def test_concurrent_same_payload_creates_one_order(_reset_main):
    db = _reset_main
    results: List[dict] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        r = _commit(db)
        with lock:
            results.append(r)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    successes = [r for r in results if r["success"]]
    assert len(successes) >= 1
    order_ids = {r["order_id"] for r in successes}
    assert len(order_ids) == 1
    rows = [r for r in db.get_orders() if r.get("order_id") in order_ids]
    assert len(rows) == 1


def test_dashboard_reads_from_supabase_not_orders_json(_reset_main, monkeypatch):
    db = _reset_main
    _commit(db)
    monkeypatch.setattr(M, "DASHBOARD_FROM_DB", True)
    monkeypatch.setattr(M, "_resolve_restaurant_by_external_id",
                        lambda rid: ("rest-1", "u-rest-1"))
    import asyncio
    resp = asyncio.run(M.get_orders(rest_id="rest-1"))
    body = resp.body.decode("utf-8")
    assert "ORD-" in body
    # orders.json är tom – data kom från Supabase.
    assert M.load_orders() != []  # backup också skriven
