#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regressionstester för Vapi kundnummer -> SMS-flödet."""

import unittest

import main


class TestCustomerPhoneExtraction(unittest.TestCase):
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

    def test_does_not_use_restaurant_contact_number_as_customer(self):
        body = {"message": {"call": {"customer": {"number": "+46760445700"}}}}
        self.assertIsNone(main._get_customer_phone_from_webhook(body))

    def test_sms_result_blocks_restaurant_contact_number(self):
        order = main.Order(
            order_id="ORD-TEST",
            items=[],
            special_requests=None,
            total_price=0,
            status="pending",
            timestamp="2026-05-13 00:00:00",
        )
        result = main._send_sms_order_confirmation_result(order, "+46760445700")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "blocked_business_or_provider_number")

    def test_extracts_phone_from_tool_params_when_vapi_sends_direct_args(self):
        body = {"message": {"call": {"to": "+46760445700"}}}
        params = {"items": [{"id": 1, "quantity": 1}], "customer_phone": "070-765 43 21"}
        self.assertEqual(main._get_customer_phone_from_webhook(body, params), "+46707654321")


if __name__ == "__main__":
    unittest.main()
