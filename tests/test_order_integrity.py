"""Unit-tester för order_integrity – payload hash, idempotency key och validering."""

import pytest

import order_integrity as oi


def _items():
    return [
        oi.CanonicalItem(item_id=1, name="Capricciosa", quantity=1, price=120.0),
        oi.CanonicalItem(item_id=10, name="Hawaii", quantity=2, price=130.0),
    ]


def test_canonical_payload_is_deterministic():
    p1 = oi.build_canonical_payload("uuid-1", _items())
    items_reversed = list(reversed(_items()))
    p2 = oi.build_canonical_payload("uuid-1", items_reversed)
    assert oi.build_payload_hash(p1) == oi.build_payload_hash(p2)


def test_payload_hash_changes_with_quantity():
    p1 = oi.build_canonical_payload("uuid-1", _items())
    altered = _items()
    altered[0].quantity = 2
    p2 = oi.build_canonical_payload("uuid-1", altered)
    assert oi.build_payload_hash(p1) != oi.build_payload_hash(p2)


def test_payload_hash_changes_with_special_requests():
    p1 = oi.build_canonical_payload("uuid-1", _items(), order_special_requests="extra ost")
    p2 = oi.build_canonical_payload("uuid-1", _items(), order_special_requests="utan ost")
    assert oi.build_payload_hash(p1) != oi.build_payload_hash(p2)


def test_idempotency_key_prefers_call_and_tool():
    h = "abc"
    k1 = oi.build_idempotency_key("uuid-1", "call-x", "tool-y", h)
    k2 = oi.build_idempotency_key("uuid-1", "call-x", "tool-y", h)
    assert k1 == k2
    assert "call-x" in k1 and "tool-y" in k1


def test_idempotency_key_falls_back_to_payload_hash_when_tool_missing():
    h = "abc"
    k = oi.build_idempotency_key("uuid-1", "call-x", None, h)
    assert "call-x" in k and h in k


def test_validate_raw_items_empty_blocks():
    with pytest.raises(oi.ValidationError) as ei:
        oi.validate_raw_items([])
    assert ei.value.error_code == "EMPTY_ORDER"


def test_validate_raw_items_quantity_zero_blocks():
    with pytest.raises(oi.ValidationError) as ei:
        oi.validate_raw_items([{"id": 1, "quantity": 0}])
    assert ei.value.error_code == "INVALID_QUANTITY"


def test_validate_raw_items_quantity_too_high_blocks():
    with pytest.raises(oi.ValidationError) as ei:
        oi.validate_raw_items([{"id": 1, "quantity": 9999}])
    assert ei.value.error_code == "QUANTITY_TOO_HIGH"


def test_validate_raw_items_special_request_too_long():
    with pytest.raises(oi.ValidationError) as ei:
        oi.validate_raw_items([{"id": 1, "quantity": 1, "special_requests": "a" * 600}])
    assert ei.value.error_code == "SPECIAL_REQUEST_TOO_LONG"


def test_safe_total_price_blocks_absurd_values():
    huge = [oi.CanonicalItem(item_id=1, name="x", quantity=oi.MAX_QUANTITY_PER_ITEM, price=999999.0)]
    with pytest.raises(oi.ValidationError) as ei:
        oi.safe_total_price(huge)
    assert ei.value.error_code == "TOTAL_PRICE_OUT_OF_RANGE"


def test_status_normalization():
    assert oi.normalize_status("nya") == "pending"
    assert oi.normalize_status("redo") == "ready"
    assert oi.normalize_status("klar") == "completed"
    assert oi.normalize_status("garbage") == "pending"
    assert oi.normalize_status("needs_review") == "needs_review"


def test_id_name_consistency_blocks_real_mismatch():
    with pytest.raises(oi.ValidationError) as ei:
        oi.validate_id_name_consistency(
            {"id": 1, "name": "Hawaii"},
            canonical_id=1,
            canonical_name="Capricciosa",
        )
    assert ei.value.error_code == "ID_NAME_MISMATCH"


def test_id_name_consistency_allows_substring_match():
    oi.validate_id_name_consistency(
        {"id": 35, "name": "kebab pizza"},
        canonical_id=35,
        canonical_name="Kebabpizza",
    )


def test_confidence_summary_flags_fuzzy_auto():
    rows = [
        {"name": "Capricciosa", "matchType": "exact"},
        {"name": "Hawaii", "matchType": "fuzzy_auto"},
    ]
    ok, low = oi.confidence_summary_for_resolved(rows)
    assert not ok
    assert len(low) == 1
    assert low[0]["match_type"] == "fuzzy_auto"
