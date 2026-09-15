"""Function-tool failures return HTTP 200 with results[].error, never 422."""

from __future__ import annotations

import asyncio
import json

import httpx

import main as M
from tests.fake_supabase import FakeSupabase


def test_failed_direct_place_order_is_http_200_with_error():
    result = {
        "name": "place_order",
        "toolCallId": "tc-fail",
        "result": json.dumps(
            {"success": False, "error": "the order must be read back and confirmed first."},
            ensure_ascii=False,
        ),
    }
    response = M._response_for_direct_place_order_result(result)
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["results"][0]["toolCallId"] == "tc-fail"
    assert body["results"][0]["error"].startswith("Order was not saved:")
    assert "read back" in body["results"][0]["error"]
    assert "result" not in body["results"][0]


def test_successful_direct_place_order_is_http_200_with_result():
    result = {
        "name": "place_order",
        "toolCallId": "tc-ok",
        "result": json.dumps({"success": True, "order_id": "ORD-1"}),
    }
    response = M._response_for_direct_place_order_result(result)
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["results"][0]["toolCallId"] == "tc-ok"
    payload = json.loads(body["results"][0]["result"])
    assert payload["success"] is True
    assert payload["order_id"] == "ORD-1"
    assert "error" not in body["results"][0]


def test_failed_webhook_tool_results_are_http_200_with_error():
    results = [
        {
            "name": "place_order",
            "toolCallId": "tc-fail",
            "result": json.dumps({"success": False, "error": "cola/fanta/sprite is 2 liter, not 1.5 liter."}),
        }
    ]
    response = M._vapi_results_response(results)
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["results"][0]["toolCallId"] == "tc-fail"
    assert "1.5 liter" in body["results"][0]["error"]


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
    body = json.loads(response.body)
    payload = json.loads(body["results"][0]["result"])
    assert payload["success"] is True
    assert payload["readback"] == "en vesuvio"


def test_draft_failure_error_does_not_claim_a_save():
    results = [
        {
            "name": "draft_order",
            "toolCallId": "tc-draft-fail",
            "result": json.dumps({"success": False, "error": "could not match xyz"}),
        }
    ]
    response = M._vapi_results_response(results)
    body = json.loads(response.body)
    assert body["results"][0]["error"] == "could not match xyz"
    assert not body["results"][0]["error"].startswith("Order was not saved:")


def _run(coro):
    return asyncio.run(coro)


def _patch_webhook(monkeypatch, tmp_path):
    db = FakeSupabase()
    db.tables["restaurants"] = [
        {"id": "tenant-uuid", "external_id": "Gislegrillen_01", "deleted_at": None}
    ]
    monkeypatch.setattr(M, "_supabase_client", db)
    monkeypatch.setattr(M, "WEBHOOK_SHARED_SECRET", "")
    monkeypatch.setattr(M, "_EFFECTIVE_WEBHOOK_SECRET", "")
    monkeypatch.setattr(M, "_get_effective_webhook_secret", lambda: "")
    monkeypatch.setattr(M, "REQUIRE_DRAFT_TOKEN", False)
    monkeypatch.setattr(M, "RESTAURANT_UUID", "tenant-uuid")
    monkeypatch.setattr(M, "ORDERS_FILE", tmp_path / "orders.json")
    M.save_orders([])
    M._MENU_CACHE.clear()
    M._CONFIG_CACHE.clear()
    M._CALL_DRAFT_CACHE.clear()
    M._ACTIVE_TENANT_UUIDS = {"tenant-uuid"}
    M._ACTIVE_TENANT_LAST_REFRESH = 10**12
    return db


def test_asgi_toolcalllist_fail_is_http_200_with_error(monkeypatch, tmp_path):
    _patch_webhook(monkeypatch, tmp_path)

    async def check():
        transport = httpx.ASGITransport(app=M.app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            response = await client.post(
                "/vapi/webhook?rest_id=Gislegrillen_01",
                json={
                    "message": {
                        "type": "tool-calls",
                        "call": {"id": "call-asgi-fail"},
                        "toolCallList": [
                            {
                                "id": "tc-asgi-fail",
                                "function": {
                                    "name": "place_order",
                                    "arguments": json.dumps(
                                        {
                                            "items": [
                                                {
                                                    "name": "1.5 liter",
                                                    "quantity": 1,
                                                    "special_requests": "cola",
                                                }
                                            ],
                                            "special_requests": "",
                                        }
                                    ),
                                },
                            }
                        ],
                    }
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["results"][0]["toolCallId"] == "tc-asgi-fail"
            assert "error" in body["results"][0]
            assert "1.5" in body["results"][0]["error"]
            assert "result" not in body["results"][0]

    _run(check())


def test_asgi_toolcalllist_ok_is_http_200_with_result(monkeypatch, tmp_path):
    _patch_webhook(monkeypatch, tmp_path)

    async def check():
        transport = httpx.ASGITransport(app=M.app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            response = await client.post(
                "/vapi/webhook?rest_id=Gislegrillen_01",
                json={
                    "message": {
                        "type": "tool-calls",
                        "call": {"id": "call-asgi-ok"},
                        "toolCallList": [
                            {
                                "id": "tc-asgi-ok",
                                "function": {
                                    "name": "draft_order",
                                    "arguments": json.dumps(
                                        {
                                            "items": [
                                                {"name": "Vesuvio", "quantity": 1}
                                            ],
                                            "special_requests": "",
                                            "service_mode": "ta_med",
                                        }
                                    ),
                                },
                            }
                        ],
                    }
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["results"][0]["toolCallId"] == "tc-asgi-ok"
            payload = json.loads(body["results"][0]["result"])
            assert payload["success"] is True
            assert "vesuvio" in payload["readback"]
            assert "error" not in body["results"][0]

    _run(check())
