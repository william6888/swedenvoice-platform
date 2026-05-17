"""
End-to-end-test för id/name-invariant i menu_match.resolve_order_items.
Säkerställer att en LLM-svit som skickar fel id med rätt namn (eller tvärtom)
inte tyst får en felaktig order, utan returneras som id_name_mismatch.
"""

import json
from pathlib import Path

import menu_match


def _build_index():
    menu = json.loads((Path(__file__).resolve().parent.parent / "menu.json").read_text(encoding="utf-8"))
    idx = menu_match.get_or_build_menu_index("test_rest", menu)
    assert idx is not None
    return idx


def test_id_only_works_normally():
    idx = _build_index()
    ok, resolved, unmatched = menu_match.resolve_order_items(
        [{"id": 1, "quantity": 1}],
        idx,
        "test_rest",
    )
    assert ok
    assert resolved[0]["id"] == 1
    assert resolved[0]["name"]


def test_id_name_mismatch_is_blocked():
    idx = _build_index()
    ok, resolved, unmatched = menu_match.resolve_order_items(
        [{"id": 1, "name": "Hawaii", "quantity": 1}],
        idx,
        "test_rest",
    )
    assert not ok
    assert len(unmatched) == 1
    assert unmatched[0]["match"]["type"] == "id_name_mismatch"
    assert unmatched[0]["match"]["sent_id"] == 1
    assert unmatched[0]["match"]["canonical_id"] == 1


def test_id_name_match_passes():
    idx = _build_index()
    ok, resolved, unmatched = menu_match.resolve_order_items(
        [{"id": 1, "name": "Capricciosa", "quantity": 1}],
        idx,
        "test_rest",
    )
    assert ok
    assert not unmatched
    assert resolved[0]["id"] == 1
    assert resolved[0]["matchType"] == "exact"


def test_id_name_substring_passes():
    idx = _build_index()
    ok, resolved, _ = menu_match.resolve_order_items(
        [{"id": 35, "name": "kebab pizza", "quantity": 2}],
        idx,
        "test_rest",
    )
    assert ok
    assert resolved[0]["id"] == 35
