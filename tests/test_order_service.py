"""Tester för order_service mot FakeSupabase."""

from tests.fake_supabase import FakeSupabase

import order_service


def test_reserve_idempotency_unique():
    db = FakeSupabase()
    ok, err = order_service.reserve_idempotency(
        db, idempotency_key="K1",
        restaurant_uuid="rest-1", restaurant_id="rest-1",
        vapi_call_id="c1", vapi_tool_call_id="t1", payload_hash="h1",
    )
    assert ok and err is None
    ok2, err2 = order_service.reserve_idempotency(
        db, idempotency_key="K1",
        restaurant_uuid="rest-1", restaurant_id="rest-1",
        vapi_call_id="c1", vapi_tool_call_id="t1", payload_hash="h1",
    )
    assert not ok2
    assert err2 == "duplicate"


def test_lookup_completed_returns_response():
    db = FakeSupabase()
    order_service.reserve_idempotency(
        db, idempotency_key="K1",
        restaurant_uuid="rest-1", restaurant_id="rest-1",
        vapi_call_id="c1", vapi_tool_call_id="t1", payload_hash="h1",
    )
    order_service.complete_idempotency(
        db, idempotency_key="K1", order_id="ORD-1", db_order_id="db-1",
        response_payload={"order_id": "ORD-1", "total_price": 120.0, "needs_human_review": False},
    )
    row, err = order_service.lookup_existing_idempotency(db, "K1")
    assert err is None
    assert row["status"] == "completed"
    assert row["order_id"] == "ORD-1"


def test_missing_table_returns_marker():
    db = FakeSupabase()
    db.simulate_missing_table["idempotency_records"] = True
    row, err = order_service.lookup_existing_idempotency(db, "K1")
    assert row is None
    assert err == "missing_table"


def test_lookup_completed_for_call_finds_first_order_for_call_id():
    db = FakeSupabase()
    order_service.reserve_idempotency(
        db, idempotency_key="K1",
        restaurant_uuid="rest-1", restaurant_id="rest-1",
        vapi_call_id="call-aaa", vapi_tool_call_id="tool-1", payload_hash="h1",
    )
    order_service.complete_idempotency(
        db, idempotency_key="K1", order_id="ORD-1", db_order_id="db-1",
        response_payload={"order_id": "ORD-1", "total_price": 120.0, "needs_human_review": False},
    )
    row, err = order_service.lookup_completed_for_call(db, "call-aaa")
    assert err is None
    assert row is not None
    assert row["order_id"] == "ORD-1"

    none_row, _ = order_service.lookup_completed_for_call(db, "call-bbb")
    assert none_row is None


def test_lookup_completed_for_call_skips_pending_rows():
    db = FakeSupabase()
    order_service.reserve_idempotency(
        db, idempotency_key="K1",
        restaurant_uuid="rest-1", restaurant_id="rest-1",
        vapi_call_id="call-pending", vapi_tool_call_id="tool-1", payload_hash="h1",
    )
    row, err = order_service.lookup_completed_for_call(db, "call-pending")
    assert err is None
    assert row is None


def test_insert_order_row_blocks_duplicate_idempotency_key():
    db = FakeSupabase()
    row = {"restaurant_id": "r", "order_id": "O1", "items": [], "total_price": 0,
           "status": "pending", "idempotency_key": "K1"}
    db_id, err = order_service.insert_order_row(db, row)
    assert db_id and err is None
    db_id2, err2 = order_service.insert_order_row(db, dict(row))
    assert err2 is not None
    assert "duplicate" in err2.lower()


def test_fetch_orders_tenant_scope():
    db = FakeSupabase()
    db.tables.setdefault("orders", []).extend([
        {"id": "1", "order_id": "A", "restaurant_uuid": "u-A", "restaurant_id": "rA",
         "items": [], "total_price": 0, "status": "pending", "created_at": "2025-01-01"},
        {"id": "2", "order_id": "B", "restaurant_uuid": "u-B", "restaurant_id": "rB",
         "items": [], "total_price": 0, "status": "pending", "created_at": "2025-01-02"},
    ])
    rows, err = order_service.fetch_orders(db, restaurant_uuid="u-A")
    assert err is None
    assert len(rows) == 1
    assert rows[0]["order_id"] == "A"


def test_update_order_status_tenant_scope_fails_for_wrong_tenant():
    db = FakeSupabase()
    db.tables.setdefault("orders", []).append(
        {"id": "1", "order_id": "A", "restaurant_uuid": "u-A", "restaurant_id": "rA", "status": "pending"}
    )
    ok, err = order_service.update_order_status(db, order_id="A", new_status="ready", restaurant_uuid="u-B")
    assert not ok
    assert err in ("not_found_or_rls", None)


def test_shape_order_for_dashboard_normalizes():
    row = {
        "order_id": "ORD-1", "items": [{"id": 1, "name": "Cap", "quantity": 1, "price": 120.0, "notes": "extra"}],
        "total_price": "120.0", "status": "Pending", "created_at": "2025-01-02T08:00Z",
        "restaurant_id": "rA", "restaurant_uuid": "u-A", "needs_human_review": True,
    }
    out = order_service.shape_order_for_dashboard(row)
    assert out["status"] == "pending"
    assert out["needs_human_review"] is True
    assert out["items"][0]["special_requests"] == "extra"
