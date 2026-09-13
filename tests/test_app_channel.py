"""Enhetstester för kundappens OTP, mobilnummer och öppettider."""

from datetime import datetime
from zoneinfo import ZoneInfo

import app_channel as C

STOCKHOLM = ZoneInfo("Europe/Stockholm")


def setup_function():
    C.reset_stores()
    C.configure_persistence(None)


def test_swedish_mobile_accepts_local_and_e164():
    assert C.swedish_mobile("070-123 45 67") == "+46701234567"
    assert C.swedish_mobile("+46 70 123 45 67") == "+46701234567"
    assert C.swedish_mobile("0046701234567") == "+46701234567"


def test_swedish_mobile_rejects_landline_and_foreign():
    assert C.swedish_mobile("031-123 45 67") is None
    assert C.swedish_mobile("+4712345678") is None
    assert C.swedish_mobile("") is None


def test_opening_hours_stockholm():
    monday_morning = datetime(2026, 9, 14, 10, 59, tzinfo=STOCKHOLM)
    monday_open = datetime(2026, 9, 14, 11, 0, tzinfo=STOCKHOLM)
    friday_late = datetime(2026, 9, 18, 21, 30, tzinfo=STOCKHOLM)
    friday_closed = datetime(2026, 9, 18, 22, 0, tzinfo=STOCKHOLM)
    sunday_last = datetime(2026, 9, 13, 20, 59, tzinfo=STOCKHOLM)
    sunday_closed = datetime(2026, 9, 13, 21, 0, tzinfo=STOCKHOLM)
    assert C.restaurant_is_open(monday_morning) is False
    assert C.restaurant_is_open(monday_open) is True
    assert C.restaurant_is_open(friday_late) is True
    assert C.restaurant_is_open(friday_closed) is False
    assert C.restaurant_is_open(sunday_last) is True
    assert C.restaurant_is_open(sunday_closed) is False


def test_otp_roundtrip_and_bad_code():
    ok, err, code = C.request_otp("+46701234567", "1.1.1.1")
    assert ok and code and len(code) == 6
    bad, msg = C.verify_otp("+46701234567", "000000")
    assert bad is False
    assert "Fel kod" in msg
    good, _ = C.verify_otp("+46701234567", code)
    assert good is True


def test_otp_rate_limit_per_phone():
    phone = "+46701234567"
    for _ in range(3):
        ok, _, _ = C.request_otp(phone, "2.2.2.2")
        assert ok
    ok, err, code = C.request_otp(phone, "2.2.2.2")
    assert ok is False
    assert code is None
    assert "För många" in err


def test_session_roundtrip():
    token = C.issue_session("+46701234567", now=1_000_000)
    assert C.verify_session(token, now=1_000_010) == "+46701234567"
    assert C.verify_session(token, now=1_000_000 + 24 * 60 * 60) == "+46701234567"
    assert C.verify_session(token, now=1_000_000 + 7 * 24 * 60 * 60 + 60) is None
    assert C.verify_session("tampered|1|nope") is None


def test_compose_special_requests_and_menu_strip():
    assert C.compose_special_requests("eat_in", "ingen lök") == "Äta här. ingen lök"
    assert C.compose_special_requests("takeaway", "") == "Ta med"
    public = C.public_menu({
        "_meta": {"modifiers": {"saser": ["Mild"]}},
        "pizzas": [{"id": 1, "name": "Margherita", "aliases": ["margarita"], "description": "Ost"}],
        "empty": [],
    })
    assert public["pizzas"][0]["id"] == 1
    assert public["pizzas"][0]["name"] == "Margherita"
    assert public["pizzas"][0]["description"] == "Ost"
    assert "aliases" not in public["pizzas"][0]
    assert public["pizzas"][0]["groups"] == [
        "pizza_storlek",
        "pizza_botten",
        "pizza_tillagg",
        "barnportion",
    ]
    mods = C.public_modifiers({
        "_meta": {"modifiers": {"saser": ["Mild", "Stark"]}},
    })
    assert [o["label"] for o in mods["modifiers"]["saser"]["options"]] == ["Mild sås", "Stark sås"]
    assert mods["modifiers"]["saser"]["label"] == "Sås"
    assert mods["modifiers"]["saser"]["selection"] == "single"


def test_public_menu_scopes_modifiers_per_dish():
    import json
    from pathlib import Path

    menu = json.loads(Path("menu.json").read_text(encoding="utf-8"))
    public = C.public_menu(menu)
    vesuvio = next(d for d in public["pizzas"] if d["name"] == "Vesuvio")
    assert vesuvio["groups"] == [
        "pizza_storlek",
        "pizza_botten",
        "pizza_tillagg",
        "barnportion",
    ]
    assert "kebabtyp" not in vesuvio["groups"]
    assert "kebabrulle_tillagg" not in vesuvio["groups"]
    assert "lchf_kott" not in vesuvio["groups"]
    assert "saser" not in vesuvio["groups"]

    kebabpizza = next(d for d in public["pizzas"] if d["name"] == "Kebabpizza")
    assert "kebabtyp" in kebabpizza["groups"]
    assert "pizza_storlek" in kebabpizza["groups"]
    assert "kebabrulle_tillagg" not in kebabpizza["groups"]

    alex = next(d for d in public["pizzas"] if "Alex" in d["name"] or "ALEX" in d["name"])
    assert "kebabtyp" not in alex["groups"]
    assert "kebabrulle_tillagg" not in alex["groups"]

    rulle = next(d for d in public["kebabs"] if d["name"] == "Kebabrulle")
    assert "pizza_storlek" not in rulle["groups"]
    assert "lchf_kott" not in rulle["groups"]
    assert "kebabrulle_tillagg" in rulle["groups"]
    assert "kebabtyp" in rulle["groups"]
    assert "saser" in rulle["groups"]

    bread = next(d for d in public["kebabs"] if d["name"] == "Kebab med bröd")
    assert "kebabrulle_tillagg" not in bread["groups"]
    assert "kebabtyp" in bread["groups"]

    drink = public["drycker"][0]
    assert drink["groups"] == []

    burger = public["hamburgare"][0]
    assert burger["groups"] == []

    lchf = public["lchf"][0]
    assert lchf["groups"] == ["lchf_kott", "sas_tillval"]

    extra_sas = next(d for d in public["tillbehor"] if d["id"] == 101)
    assert extra_sas["name"] == "Sås"
    assert extra_sas["groups"] == ["sas_storlek", "extra_sas_smak"]
    assert extra_sas["price"] == 10
    assert extra_sas["price_large"] == 18
    assert "price_family" not in extra_sas
    assert all(d["id"] != 100 for d in public["tillbehor"])
    assert all(d["id"] != 62 for d in public.get("sallader", []))
    assert all(d["id"] != 106 for d in public.get("drycker", []))

    mods = C.public_modifiers(menu)
    assert mods["modifiers"]["pizza_storlek"]["label"] == "Storlek"
    assert mods["modifiers"]["pizza_storlek"]["default"] == "Standard"
    assert mods["modifiers"]["pizza_storlek"]["options"][0]["label"] == "Standard"
    assert mods["modifiers"]["pizza_storlek"]["required"] is True
    assert mods["modifiers"]["pizza_botten"]["label"] == "Botten"
    tillagg = [o["label"] for o in mods["modifiers"]["pizza_tillagg"]["options"]]
    rulle = [o["label"] for o in mods["modifiers"]["kebabrulle_tillagg"]["options"]]
    assert mods["modifiers"]["pizza_tillagg"]["label"] == "Extra topping"
    assert "Barnportion" not in tillagg
    assert "Extra Fläskfilé" in tillagg
    extra_ost = next(o for o in mods["modifiers"]["pizza_tillagg"]["options"] if o["label"] == "Extra Ost")
    assert extra_ost["price"] == 15
    gluten = next(o for o in mods["modifiers"]["pizza_botten"]["options"] if "Glutenfri" in o["label"])
    assert gluten["price"] == 30
    assert "Barnportion" not in rulle
    assert mods["modifiers"]["barnportion"]["options"][0]["label"] == "Barnportion"
    assert mods["modifiers"]["barnportion"]["options"][0]["price"] == -10
    assert mods["modifiers"]["barnportion"]["label"] == "Barn?"
    assert mods["modifiers"]["pizza_tillagg"]["selection"] == "multi"
    assert mods["modifiers"]["sas_storlek"]["label"] == "Storlek"
    assert mods["modifiers"]["sas_storlek"]["required"] is True
    assert mods["modifiers"]["sas_storlek"]["default"] == "Liten"
    assert [o["label"] for o in mods["modifiers"]["sas_storlek"]["options"]] == ["Liten", "Stor"]
    assert mods["modifiers"]["extra_sas_smak"]["label"] == "Smak"
    assert mods["modifiers"]["extra_sas_smak"]["required"] is True
    assert [o["label"] for o in mods["modifiers"]["extra_sas_smak"]["options"]] == [
        "Mild",
        "Stark",
        "Vitlök",
        "Laktosfri",
    ]
    assert mods["modifiers"]["sas_tillval"]["required"] is False
    assert "kebabtyp" not in mods["category_groups"]["pizzas"]
    capricciosa = next(d for d in public["pizzas"] if d["name"] == "Capricciosa")
    assert capricciosa["price"] == 130
    assert capricciosa["price_family"] == 320
    ibbe = next(d for d in public["pizzas"] if "Ibbe" in d["name"])
    assert ibbe["name"] == "Ibbe-Special"
    assert ibbe["price"] == 160
    assert ibbe["price_family"] == 380
    assert C.CATEGORY_LABELS["pizzas"] == "Pizza"
    assert C.CATEGORY_LABELS["sallader"] == "Sallader"


def test_extra_sas_groups_exist_without_menu_meta():
    mods = C.public_modifiers({"_meta": {"modifiers": {"saser": ["Mild"]}}})
    assert mods["modifiers"]["sas_storlek"]["default"] == "Liten"
    assert [o["label"] for o in mods["modifiers"]["extra_sas_smak"]["options"]] == [
        "Mild",
        "Stark",
        "Vitlök",
        "Laktosfri",
    ]
    public = C.public_menu({
        "tillbehor": [{"id": 101, "name": "Extra sås", "description": ""}],
    })
    assert public["tillbehor"][0]["groups"] == ["sas_storlek", "extra_sas_smak"]
    assert public["tillbehor"][0]["price_large"] == 18


def test_server_prices_ignore_client_and_use_qopla():
    import json
    from pathlib import Path

    menu = json.loads(Path("menu.json").read_text(encoding="utf-8"))
    assert C.unit_price(1, "Standard, Vanlig botten", menu) == 130
    assert C.unit_price(1, "Familj, Glutenfri botten", menu) == 350
    assert C.unit_price(1, "standard, extra ost", menu) == 145
    assert C.unit_price(54, "Pommes", menu) == 155
    assert C.unit_price(101, "Liten, Mild", menu) == 10
    assert C.unit_price(101, "Stor, Mild", menu) == 18
    assert C.unit_price(101, "Stor, Vitlök", menu) == 18
    assert C.unit_price(101, "Mild", menu) == 10


def test_required_groups_and_reviewer_otp(monkeypatch):
    import json
    from pathlib import Path

    menu = json.loads(Path("menu.json").read_text(encoding="utf-8"))
    published = C.public_modifiers(menu)["modifiers"]
    extra = {"id": 101, "name": "Sås"}
    assert "Smak" in C.missing_required_groups("tillbehor", extra, "Stor", published)
    assert C.missing_required_groups("tillbehor", extra, "Stor, Mild", published) == []
    vesuvio = {"id": 2, "name": "Vesuvio", "description": "Skinka"}
    assert "Storlek" in C.missing_required_groups("pizzas", vesuvio, "", published)
    assert C.missing_required_groups(
        "pizzas", vesuvio, "Standard, Vanlig botten", published
    ) == []

    monkeypatch.setenv("APP_REVIEW_PHONE", "0709998877")
    monkeypatch.setenv("APP_REVIEW_CODE", "654321")
    phone = C.swedish_mobile("0709998877")
    assert C.is_reviewer_phone(phone)
    ok, _, code = C.request_otp(phone, "8.8.8.8")
    assert ok and code == "654321"
    good, _ = C.verify_otp(phone, "654321")
    assert good is True


def test_otp_survives_memory_clear():
    from tests.fake_supabase import FakeSupabase

    db = FakeSupabase()
    C.configure_persistence(db)
    try:
        ok, _, code = C.request_otp("+46701234567", "3.3.3.3")
        assert ok and code
        C._OTP_STORE.clear()
        good, _ = C.verify_otp("+46701234567", code)
        assert good is True
    finally:
        C.configure_persistence(None)
