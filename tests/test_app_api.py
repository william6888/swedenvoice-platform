"""HTTP-tester för kundappens /app-API."""

import asyncio
import re

import httpx

import app_channel
import main
from tests.fake_supabase import FakeSupabase


def _db() -> FakeSupabase:
    db = FakeSupabase()
    db.tables["restaurants"] = [
        {"id": "tenant-uuid", "external_id": "Gislegrillen_01", "deleted_at": None}
    ]
    return db


def _run(coro):
    return asyncio.run(coro)


def _transport():
    return httpx.ASGITransport(app=main.app)


def _patch_app(monkeypatch, tmp_path):
    db = _db()
    monkeypatch.setattr(main, "_supabase_client", db)
    monkeypatch.setattr(main, "ORDER_REQUIRE_DB_COMMIT", True)
    monkeypatch.setattr(main, "RESTAURANT_UUID", "tenant-uuid")
    monkeypatch.setattr(app_channel, "restaurant_is_open", lambda now=None: True)
    monkeypatch.setattr(main.app_channel, "restaurant_is_open", lambda now=None: True)
    monkeypatch.setattr(main, "_sms_sender_for_worker", lambda to, body: {"ok": True, "to": to})
    monkeypatch.setattr(main, "send_customer_sms_now", lambda *a, **k: None)
    monkeypatch.setattr(main, "ORDERS_FILE", tmp_path / "orders.json")
    main.save_orders([])
    main._MENU_CACHE.clear()
    app_channel.reset_stores()
    return db


def test_app_menu_is_public_and_has_cors(monkeypatch, tmp_path):
    _patch_app(monkeypatch, tmp_path)

    async def check():
        async with httpx.AsyncClient(transport=_transport(), base_url="https://testserver") as client:
            app_origin = {"Origin": "https://gislegrillen.lovable.app"}
            options = await client.options("/app/menu", headers=app_origin)
            assert options.status_code == 204
            assert options.headers.get("access-control-allow-origin") == "https://gislegrillen.lovable.app"
            blocked = await client.options("/app/menu", headers={"Origin": "https://evil.example"})
            assert blocked.status_code == 204
            assert blocked.headers.get("access-control-allow-origin") is None
            menu = await client.get("/app/menu", headers=app_origin)
            assert menu.status_code == 200
            body = menu.json()
            assert body["ok"] is True
            assert "pizzas" in body["categories"]
            vesuvio = next(d for d in body["categories"]["pizzas"] if d["name"] == "Vesuvio")
            assert "aliases" not in vesuvio
            assert "kebabrulle_tillagg" not in vesuvio["groups"]
            assert "lchf_kott" not in vesuvio["groups"]
            assert "kebabtyp" in vesuvio["groups"]
            assert vesuvio["price"] == 130
            assert vesuvio["price_family"] == 320
            assert body["category_labels"]["pizzas"] == "Pizza"
            assert body["modifiers"]["modifiers"]["pizza_storlek"]["label"] == "Storlek"
            assert body["modifiers"]["modifiers"]["pizza_storlek"]["default"] == "Standard"
            assert body["modifiers"]["modifiers"]["pizza_botten"]["label"] == "Smak"
            extra = next(
                o for o in body["modifiers"]["modifiers"]["pizza_tillagg"]["options"]
                if o["label"] == "Extra Ost"
            )
            assert extra["price"] == 15
            assert menu.headers.get("access-control-allow-origin") == "https://gislegrillen.lovable.app"

    _run(check())


def test_bad_otp_is_rejected(monkeypatch, tmp_path):
    _patch_app(monkeypatch, tmp_path)

    async def check():
        async with httpx.AsyncClient(transport=_transport(), base_url="https://testserver") as client:
            sent = await client.post("/app/otp/request", json={"phone": "0701234567"})
            assert sent.status_code == 200
            bad = await client.post(
                "/app/otp/verify",
                json={"phone": "0701234567", "code": "000000"},
            )
            assert bad.status_code == 401
            assert bad.json()["ok"] is False

    _run(check())


def test_fake_pizza_is_rejected(monkeypatch, tmp_path):
    _patch_app(monkeypatch, tmp_path)
    ok, _, code = app_channel.request_otp("+46701234567", "9.9.9.9")
    assert ok
    session = None

    async def check():
        nonlocal session
        async with httpx.AsyncClient(transport=_transport(), base_url="https://testserver") as client:
            verify = await client.post(
                "/app/otp/verify",
                json={"phone": "0701234567", "code": code},
            )
            assert verify.status_code == 200
            session = verify.json()["session"]
            response = await client.post(
                "/app/orders",
                headers={"X-App-Session": session},
                json={
                    "customer_name": "Testare",
                    "service_mode": "takeaway",
                    "client_request_id": "fake-pizza-1",
                    "items": [{"name": "Unicorn Pizza", "quantity": 1}],
                },
            )
            assert response.status_code == 422
            assert response.json()["ok"] is False

    _run(check())
    assert main._supabase_client.get_orders() == []


def test_cola_one_point_five_becomes_two_liter(monkeypatch, tmp_path):
    db = _patch_app(monkeypatch, tmp_path)
    captured = {}

    def capture_sms(to, body):
        captured["body"] = body
        return {"ok": True, "to": to}

    monkeypatch.setattr(main, "_sms_sender_for_worker", capture_sms)

    async def check():
        async with httpx.AsyncClient(transport=_transport(), base_url="https://testserver") as client:
            asked = await client.post("/app/otp/request", json={"phone": "+46701234567"})
            assert asked.status_code == 200
            code = re.search(r"(\d{6})", captured["body"]).group(1)
            verify = await client.post(
                "/app/otp/verify",
                json={"phone": "+46701234567", "code": code},
            )
            session = verify.json()["session"]
            response = await client.post(
                "/app/orders",
                headers={"Authorization": f"Bearer {session}"},
                json={
                    "customer_name": "Anna",
                    "service_mode": "takeaway",
                    "client_request_id": "cola-rewrite-1",
                    "items": [{"name": "1.5 liter", "quantity": 1, "notes": "cola"}],
                },
            )
            assert response.status_code == 200, response.text
            assert response.json()["ok"] is True

    _run(check())
    rows = db.get_orders()
    assert len(rows) == 1
    assert rows[0]["source"] == "app"
    assert rows[0]["items"][0]["name"] == "2 liter"
    assert "Ta med" in (rows[0].get("special_instructions") or "")


def test_orders_rejected_when_closed(monkeypatch, tmp_path):
    _patch_app(monkeypatch, tmp_path)
    monkeypatch.setattr(app_channel, "restaurant_is_open", lambda now=None: False)
    monkeypatch.setattr(main.app_channel, "restaurant_is_open", lambda now=None: False)

    async def check():
        async with httpx.AsyncClient(transport=_transport(), base_url="https://testserver") as client:
            response = await client.post("/app/otp/request", json={"phone": "0701234567"})
            assert response.status_code == 403
            assert response.json()["error"] == "closed"

    _run(check())


def test_app_order_uses_server_qopla_price(monkeypatch, tmp_path):
    db = _patch_app(monkeypatch, tmp_path)
    captured = {}

    def capture_sms(to, body):
        captured["body"] = body
        return {"ok": True, "to": to}

    monkeypatch.setattr(main, "_sms_sender_for_worker", capture_sms)

    async def check():
        async with httpx.AsyncClient(transport=_transport(), base_url="https://testserver") as client:
            asked = await client.post("/app/otp/request", json={"phone": "+46701234567"})
            assert asked.status_code == 200
            code = re.search(r"(\d{6})", captured["body"]).group(1)
            verify = await client.post(
                "/app/otp/verify",
                json={"phone": "+46701234567", "code": code},
            )
            session = verify.json()["session"]
            response = await client.post(
                "/app/orders",
                headers={"X-App-Session": session},
                json={
                    "customer_name": "Anna",
                    "service_mode": "takeaway",
                    "client_request_id": "priced-cap-1",
                    "items": [{
                        "id": 1,
                        "name": "Capricciosa",
                        "quantity": 1,
                        "notes": "Familj, Glutenfri botten",
                    }],
                },
            )
            assert response.status_code == 200, response.text
            assert response.json()["total_price"] == 350

    _run(check())
    rows = db.get_orders()
    assert rows[0]["items"][0]["price"] == 350


def test_landline_cannot_request_otp(monkeypatch, tmp_path):
    _patch_app(monkeypatch, tmp_path)

    async def check():
        async with httpx.AsyncClient(transport=_transport(), base_url="https://testserver") as client:
            response = await client.post("/app/otp/request", json={"phone": "0311234567"})
            assert response.status_code == 400

    _run(check())
