"""Tester för draft-tokens (HMAC-signerad confirmation)."""

import time

import confirmation


def test_issue_and_verify_token_roundtrip():
    token, payload = confirmation.issue_draft_token(
        restaurant_uuid="rest-1",
        payload_hash="hash-a",
        items_summary=[{"id": 1, "name": "Capri", "quantity": 1}],
        total_price=120.0,
        needs_human_review=False,
    )
    ok, decoded, err = confirmation.verify_draft_token(
        token, expected_restaurant_uuid="rest-1", expected_payload_hash="hash-a"
    )
    assert ok
    assert err is None
    assert decoded["restaurant_uuid"] == "rest-1"


def test_token_rejects_hash_drift():
    token, _ = confirmation.issue_draft_token(
        restaurant_uuid="rest-1",
        payload_hash="hash-a",
        items_summary=[],
        total_price=0.0,
        needs_human_review=False,
    )
    ok, _, err = confirmation.verify_draft_token(
        token, expected_restaurant_uuid="rest-1", expected_payload_hash="hash-b"
    )
    assert not ok
    assert err == "HASH_MISMATCH"


def test_token_rejects_expired():
    token, _ = confirmation.issue_draft_token(
        restaurant_uuid="rest-1",
        payload_hash="hash-a",
        items_summary=[],
        total_price=0.0,
        needs_human_review=False,
        ttl_seconds=30,
    )
    ok, _, err = confirmation.verify_draft_token(
        token,
        expected_restaurant_uuid="rest-1",
        expected_payload_hash="hash-a",
        now=time.time() + 3600,
    )
    assert not ok
    assert err == "EXPIRED"


def test_token_rejects_tampered_signature():
    token, _ = confirmation.issue_draft_token(
        restaurant_uuid="rest-1",
        payload_hash="hash-a",
        items_summary=[],
        total_price=0.0,
        needs_human_review=False,
    )
    body, sig = token.rsplit(".", 1)
    bad = body + "." + ("A" * len(sig))
    ok, _, err = confirmation.verify_draft_token(
        bad, expected_restaurant_uuid="rest-1", expected_payload_hash="hash-a"
    )
    assert not ok
    assert err == "INVALID_SIGNATURE"


def test_token_rejects_restaurant_mismatch():
    token, _ = confirmation.issue_draft_token(
        restaurant_uuid="rest-1",
        payload_hash="hash-a",
        items_summary=[],
        total_price=0.0,
        needs_human_review=False,
    )
    ok, _, err = confirmation.verify_draft_token(
        token, expected_restaurant_uuid="rest-OTHER", expected_payload_hash="hash-a"
    )
    assert not ok
    assert err == "RESTAURANT_MISMATCH"


def test_canonical_readback_format():
    text = confirmation.format_canonical_readback(
        [{"id": 1, "name": "Capri", "quantity": 2}],
        240.0,
        special_requests="extra ost",
    )
    assert "2 Capri" in text
    assert "Speciellt: extra ost" in text
    assert "Totalt: 240" in text


def test_verbal_readback_no_prices():
    text = confirmation.format_verbal_readback(
        [{"id": 1, "name": "Capri", "quantity": 2}],
        special_requests="extra ost",
    )
    assert "2 Capri" in text
    assert "kr" not in text
    assert "Speciellt: extra ost" in text
