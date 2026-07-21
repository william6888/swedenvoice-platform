#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regressionstester för Vapi kundnummer -> SMS-flödet."""

import unittest

import main


class TestCustomerPhoneExtraction(unittest.TestCase):
    def setUp(self):
        # Enhetstester får aldrig ärva live-klienten från main.py/.env och skriva
        # call_state till produktion.
        self._original_supabase = main._supabase_client
        main._supabase_client = None
        main._CALL_CUSTOMER_PHONE_CACHE.clear()

    def tearDown(self):
        main._CALL_CUSTOMER_PHONE_CACHE.clear()
        main._supabase_client = self._original_supabase

    def test_env_values_are_trimmed_for_strict_api_auth(self):
        self.assertEqual(main._clean_env_value("__MISSING_TEST_ENV__", " fallback\t"), "fallback")

    def test_extracts_customer_number_from_vapi_call(self):
        body = {
            "message": {
                "call": {
                    "customer": {"number": "070 123 45 67"},
                    "to": "+46760445700",
                }
            }
        }
        self.assertEqual(main._get_customer_phone_from_webhook(body), "+46701234567")

    def test_extracts_inbound_from_when_customer_object_is_missing(self):
        body = {
            "message": {
                "call": {
                    "from": "+46701234567",
                    "to": "+46760445700",
                    "phoneNumber": {"number": "+46760445700"},
                }
            }
        }
        self.assertEqual(main._get_customer_phone_from_webhook(body), "+46701234567")

    def test_does_not_use_destination_or_business_number_as_customer(self):
        body = {
            "message": {
                "call": {
                    "to": "+46760445700",
                    "phoneNumber": {"number": "+46760445700"},
                }
            }
        }
        self.assertIsNone(main._get_customer_phone_from_webhook(body))

    def test_uses_customer_number_even_if_it_matches_old_hardcoded_value(self):
        body = {"message": {"call": {"customer": {"number": "+46760445700"}}}}
        self.assertEqual(main._get_customer_phone_from_webhook(body), "+46760445700")

    def test_sms_blocks_explicitly_excluded_number(self):
        original = main.RESTAURANT_CONTACT_NUMBER
        main.RESTAURANT_CONTACT_NUMBER = "+46769439831"
        try:
            order = main.Order(
                order_id="ORD-TEST",
                items=[],
                special_requests=None,
                total_price=0,
                status="pending",
                timestamp="2026-05-13 00:00:00",
            )
            result = main._send_sms_order_confirmation_result(order, "+46769439831")
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "blocked_business_or_provider_number")
        finally:
            main.RESTAURANT_CONTACT_NUMBER = original

    def test_extracts_phone_from_tool_params_when_vapi_sends_direct_args(self):
        body = {"message": {"call": {"to": "+46760445700"}}}
        params = {"items": [{"id": 1, "quantity": 1}], "customer_phone": "070-765 43 21"}
        self.assertEqual(main._get_customer_phone_from_webhook(body, params), "+46707654321")

    def test_resolve_customer_phone_uses_vapi_api_when_webhook_lacks_customer(self):
        body = {
            "message": {
                "type": "tool-calls",
                "call": {"id": "call-test-123", "to": "+46769439831"},
            }
        }
        original_fetch = main._fetch_vapi_call_record
        try:
            main._fetch_vapi_call_record = lambda _cid: {
                "id": "call-test-123",
                "customer": {"number": "+46701234567"},
            }
            self.assertEqual(main._resolve_customer_phone(body, {}), "+46701234567")
            self.assertEqual(main._get_cached_customer_phone_for_call("call-test-123"), "+46701234567")
        finally:
            main._fetch_vapi_call_record = original_fetch

    def test_resolve_customer_phone_returns_default_caller_id(self):
        body = {"message": {"call": {"id": "call-blocked-1"}}}
        original_fetch = main._fetch_vapi_call_record
        try:
            main._fetch_vapi_call_record = lambda _cid: {
                "customer": {"number": "+46760445700"},
            }
            self.assertEqual(main._resolve_customer_phone(body, {}), "+46760445700")
        finally:
            main._fetch_vapi_call_record = original_fetch

    def test_direct_place_order_payload_is_detected(self):
        body = {"items": [{"name": "Vesuvio", "quantity": 1}], "special_requests": ""}
        self.assertTrue(main._looks_like_place_order_params(body))
        self.assertEqual(main._params_from_direct_place_order_payload(body), body)

    def test_dagens_is_not_a_menu_item(self):
        body = {"items": [{"name": "dagens rätt", "quantity": 1}]}
        items = main._parse_items_from_params(body, "Gislegrillen_01")
        ok, _resolved, fail_json = main._resolve_items_with_menu_match(items, "Gislegrillen_01")
        self.assertFalse(ok)
        self.assertIn("dagens rätt", fail_json)


if __name__ == "__main__":
    unittest.main()
