#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests för menu_match v2.1 (WRatio, kollision, multi-item)."""

import json
import unittest
from pathlib import Path

import menu_match


class TestNormalize(unittest.TestCase):
    def test_hyphen_and_diacritics(self):
        self.assertEqual(menu_match.normalize("Ciao-Ciao"), "ciao ciao")
        self.assertEqual(menu_match.normalize("Wärdshusschnitzel"), "wardshusschnitzel")

    def test_whitespace(self):
        self.assertEqual(menu_match.normalize("  Foo   Bar  "), "foo bar")

    def test_gram_suffix(self):
        self.assertIn("gram", menu_match.normalize("90g i bröd"))


class TestCollision(unittest.TestCase):
    def test_collision_removes_key_from_lookup(self):
        menu = {
            "pizzas": [
                {"id": 1, "name": "Foo Bar", "price": 100, "description": ""},
                {"id": 2, "name": "Foo-Bar", "price": 100, "description": ""},
            ]
        }
        idx = menu_match.build_menu_index(menu, "test")
        self.assertIn("foo bar", idx.colliding_keys)
        self.assertNotIn("foo bar", idx.lookup)


class TestExactAndAlias(unittest.TestCase):
    def test_margarita_alias(self):
        root = Path(__file__).resolve().parent.parent
        with open(root / "menu.json", "r", encoding="utf-8") as f:
            menu = json.load(f)
        idx = menu_match.build_menu_index(menu, "g1")
        m = idx.match_one("margarita", "g1")
        self.assertEqual(m["type"], "alias")
        self.assertEqual(m["itemId"], 3)
        self.assertEqual(m["canonicalName"], "Margherita")

    def test_ciao_alias(self):
        root = Path(__file__).resolve().parent.parent
        with open(root / "menu.json", "r", encoding="utf-8") as f:
            menu = json.load(f)
        idx = menu_match.build_menu_index(menu, "g1")
        m = idx.match_one("ciao", "g1")
        self.assertIn(m["type"], ("exact", "alias"))
        self.assertEqual(m["itemId"], 25)


class TestFuzzyAuto(unittest.TestCase):
    def test_capriciosa(self):
        root = Path(__file__).resolve().parent.parent
        with open(root / "menu.json", "r", encoding="utf-8") as f:
            menu = json.load(f)
        idx = menu_match.build_menu_index(menu, "g1")
        m = idx.match_one("capriciosa", "g1")
        self.assertIn(m["type"], ("fuzzy_auto", "alias"))
        self.assertEqual(m["itemId"], 1)


class TestFuzzyAmbiguous(unittest.TestCase):
    def test_cal_gives_ambiguous_or_auto(self):
        root = Path(__file__).resolve().parent.parent
        with open(root / "menu.json", "r", encoding="utf-8") as f:
            menu = json.load(f)
        idx = menu_match.build_menu_index(menu, "g1")
        m = idx.match_one("cal", "g1")
        self.assertIn(m["type"], ("fuzzy_ambiguous", "fuzzy_auto"))
        if m["type"] == "fuzzy_ambiguous":
            self.assertIn("Calzone", m["suggestions"])


class TestResolveMulti(unittest.TestCase):
    def setUp(self):
        menu_match.invalidate_menu_index_cache(None)

    def test_multi_one_no_match(self):
        menu = {
            "pizzas": [
                {"id": 1, "name": "Hawaii", "price": 100, "description": ""},
            ]
        }
        idx = menu_match.build_menu_index(menu, "t")
        rows = [
            {"name": "Hawaii", "quantity": 1},
            {"name": "notarealnamezzz", "quantity": 2},
        ]
        ok, resolved, unmatched = menu_match.resolve_order_items(rows, idx, "t")
        self.assertFalse(ok)
        self.assertEqual(len(unmatched), 1)
        self.assertEqual(unmatched[0]["index"], 1)
        self.assertEqual(unmatched[0]["match"]["type"], "no_match")

    def test_multi_all_ok(self):
        menu = {
            "pizzas": [
                {"id": 1, "name": "Hawaii", "price": 100, "description": ""},
                {"id": 2, "name": "Vesuvio", "price": 100, "description": ""},
            ]
        }
        idx = menu_match.build_menu_index(menu, "t")
        rows = [
            {"name": "Hawaii", "quantity": 1},
            {"name": "Vesuvio", "quantity": 2},
        ]
        ok, resolved, unmatched = menu_match.resolve_order_items(rows, idx, "t")
        self.assertTrue(ok)
        self.assertEqual(len(resolved), 2)
        self.assertEqual(resolved[0]["id"], 1)
        self.assertEqual(resolved[1]["id"], 2)


class TestEmptyMenu(unittest.TestCase):
    def test_menu_has_items_false(self):
        self.assertFalse(menu_match.menu_has_items({}))
        self.assertFalse(menu_match.menu_has_items({"pizzas": []}))

    def test_fail_json_shape(self):
        s = menu_match.place_order_fail_json("Testfel", [])
        d = json.loads(s)
        self.assertFalse(d["success"])
        self.assertEqual(d["error"], "Testfel")
        self.assertEqual(d["unmatchedItems"], [])


class TestRestIdCache(unittest.TestCase):
    def setUp(self):
        menu_match.invalidate_menu_index_cache(None)

    def test_indexes_differ(self):
        m1 = {"pizzas": [{"id": 1, "name": "A", "price": 1, "description": ""}]}
        m2 = {"pizzas": [{"id": 99, "name": "B", "price": 1, "description": ""}]}
        i1 = menu_match.get_or_build_menu_index("r1", m1)
        i2 = menu_match.get_or_build_menu_index("r2", m2)
        self.assertEqual(i1.lookup[menu_match.normalize("a")], 1)
        self.assertEqual(i2.lookup[menu_match.normalize("b")], 99)


if __name__ == "__main__":
    unittest.main()
