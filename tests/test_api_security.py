"""API-säkerhet: dashboard-auth, tenant fail-closed och status-scope."""

import asyncio

import httpx
import main
from tests.fake_supabase import FakeSupabase


def _configured_db() -> FakeSupabase:
    db = FakeSupabase()
    db.tables["restaurants"] = [
        {
            "id": "tenant-uuid",
            "external_id": "Gislegrillen_01",
            "deleted_at": None,
        }
    ]
    db.tables["orders"] = [
        {
            "id": "db-1",
            "order_id": "ORD-1",
            "restaurant_uuid": "tenant-uuid",
            "restaurant_id": "Gislegrillen_01",
            "status": "pending",
            "items": [],
            "created_at": "2026-07-21T08:00:00Z",
        }
    ]
    return db


def _run(coro):
    return asyncio.run(coro)


def _transport():
    return httpx.ASGITransport(app=main.app)


def test_dashboard_data_and_status_are_denied_without_auth():
    async def check():
        async with httpx.AsyncClient(
            transport=_transport(), base_url="https://testserver"
        ) as client:
            assert (await client.get("/dashboard")).status_code == 401
            assert (await client.get("/orders")).status_code == 401
            response = await client.post(
                "/update_order_status",
                json={"order_id": "ORD-1", "status": "ready"},
            )
            assert response.status_code == 401

    _run(check())


def test_dashboard_login_sets_session_and_serves_html(monkeypatch):
    monkeypatch.setattr(main, "DASHBOARD_ACCESS_KEY", "dashboard-test-key")

    async def check():
        async with httpx.AsyncClient(
            transport=_transport(), base_url="https://testserver"
        ) as client:
            login = await client.post(
                "/dashboard/login", json={"key": "dashboard-test-key"}
            )
            assert login.status_code == 200
            response = await client.get("/dashboard")
            assert response.status_code == 200
            assert "Gislegrillen" in response.text

    _run(check())


def test_dashboard_login_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(main, "DASHBOARD_ACCESS_KEY", "right-key")

    async def check():
        async with httpx.AsyncClient(
            transport=_transport(), base_url="https://testserver"
        ) as client:
            response = await client.post(
                "/dashboard/login", json={"key": "wrong-key"}
            )
            assert response.status_code == 401
            assert main._DASHBOARD_COOKIE_NAME not in response.cookies

    _run(check())


def test_unknown_tenant_does_not_receive_default_menu(monkeypatch):
    monkeypatch.setattr(main, "_supabase_client", _configured_db())
    main._MENU_CACHE.clear()

    async def check():
        async with httpx.AsyncClient(
            transport=_transport(), base_url="https://testserver"
        ) as client:
            response = await client.get("/menu?rest_id=does-not-exist")
            assert response.status_code == 404

    _run(check())


def test_unknown_tenant_file_fallback_is_empty():
    menu = main.load_menu("does-not-exist")

    assert not any(
        isinstance(category, list) and category
        for category in menu.values()
    )


def test_authenticated_status_update_is_tenant_scoped(monkeypatch):
    db = _configured_db()
    monkeypatch.setattr(main, "_supabase_client", db)
    monkeypatch.setattr(main, "DASHBOARD_FROM_DB", True)
    monkeypatch.setattr(main, "DASHBOARD_ACCESS_KEY", "dashboard-test-key")

    async def check():
        async with httpx.AsyncClient(
            transport=_transport(), base_url="https://testserver"
        ) as client:
            await client.post(
                "/dashboard/login", json={"key": "dashboard-test-key"}
            )
            response = await client.post(
                "/update_order_status?rest_id=Gislegrillen_01",
                json={"order_id": "ORD-1", "status": "ready"},
            )
            assert response.status_code == 200

    _run(check())
    assert db.tables["orders"][0]["status"] == "ready"


def test_authenticated_status_update_rejects_unknown_tenant(monkeypatch):
    db = _configured_db()
    monkeypatch.setattr(main, "_supabase_client", db)
    monkeypatch.setattr(main, "DASHBOARD_FROM_DB", True)
    monkeypatch.setattr(main, "DASHBOARD_ACCESS_KEY", "dashboard-test-key")

    async def check():
        async with httpx.AsyncClient(
            transport=_transport(), base_url="https://testserver"
        ) as client:
            await client.post(
                "/dashboard/login", json={"key": "dashboard-test-key"}
            )
            response = await client.post(
                "/update_order_status?rest_id=does-not-exist",
                json={"order_id": "ORD-1", "status": "ready"},
            )
            assert response.status_code == 404

    _run(check())
    assert db.tables["orders"][0]["status"] == "pending"
