"""Failed Vapi tools must not return HTTP 2xx, or request-complete/goodbye plays anyway."""

from __future__ import annotations

import json

import main as M


def test_failed_direct_place_order_is_http_422():
    result = {
        "name": "place_order",
        "toolCallId": "tc-fail",
        "result": json.dumps(
            {"success": False, "error": "Beställningen måste valideras och läsas upp igen."},
            ensure_ascii=False,
        ),
    }
    response = M._response_for_direct_place_order_result(result)
    assert response.status_code == 422
    body = json.loads(response.body)
    assert body["success"] is False


def test_successful_direct_place_order_is_http_200():
    result = {
        "name": "place_order",
        "toolCallId": "tc-ok",
        "result": json.dumps({"success": True, "order_id": "ORD-1"}),
    }
    response = M._response_for_direct_place_order_result(result)
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["success"] is True
    assert body["order_id"] == "ORD-1"


def test_failed_webhook_tool_results_are_http_422():
    results = [
        {
            "name": "place_order",
            "toolCallId": "tc-fail",
            "result": json.dumps({"success": False, "error": "Temporärt fel."}),
        }
    ]
    response = M._vapi_results_response(results)
    assert response.status_code == 422


def test_successful_webhook_tool_results_are_http_200():
    results = [
        {
            "name": "draft_order",
            "toolCallId": "tc-ok",
            "result": json.dumps({"success": True, "readback": "en vesuvio"}),
        }
    ]
    response = M._vapi_results_response(results)
    assert response.status_code == 200
