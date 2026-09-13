"""Enhetstester för kundappens OTP, mobilnummer och öppettider."""

from datetime import datetime
from zoneinfo import ZoneInfo

import app_channel as C

STOCKHOLM = ZoneInfo("Europe/Stockholm")


def setup_function():
    C.reset_stores()


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
    assert C.verify_session(token, now=1_000_000 + 21 * 60) is None
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
        "kebabtyp",
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
        "kebabtyp",
        "pizza_tillagg",
        "barnportion",
    ]
    assert "kebabrulle_tillagg" not in vesuvio["groups"]
    assert "lchf_kott" not in vesuvio["groups"]
    assert "saser" not in vesuvio["groups"]

    kebabpizza = next(d for d in public["pizzas"] if d["name"] == "Kebabpizza")
    assert "kebabtyp" in kebabpizza["groups"]
    assert "pizza_storlek" in kebabpizza["groups"]
    assert "kebabrulle_tillagg" not in kebabpizza["groups"]

    alex = next(d for d in public["pizzas"] if "Alex" in d["name"] or "ALEX" in d["name"])
    assert "kebabtyp" in alex["groups"]
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

    mods = C.public_modifiers(menu)
    assert mods["modifiers"]["pizza_storlek"]["label"] == "Storlek"
    assert mods["modifiers"]["pizza_storlek"]["default"] == "Standard"
    assert mods["modifiers"]["pizza_storlek"]["options"][0]["label"] == "Standard"
    assert mods["modifiers"]["pizza_storlek"]["required"] is True
    assert mods["modifiers"]["pizza_botten"]["label"] == "Smak"
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
    assert "kebabtyp" in mods["category_groups"]["pizzas"]
    capricciosa = next(d for d in public["pizzas"] if d["name"] == "Capricciosa")
    assert capricciosa["price"] == 130
    assert capricciosa["price_family"] == 320
    ibbe = next(d for d in public["pizzas"] if "Ibbe" in d["name"])
    assert ibbe["name"] == "Ibbe-Special"
    assert ibbe["price"] == 160
    assert ibbe["price_family"] == 380
    assert C.CATEGORY_LABELS["pizzas"] == "Pizza"
    assert C.CATEGORY_LABELS["sallader"] == "Sallader"


def test_server_prices_ignore_client_and_use_qopla():
    import json
    from pathlib import Path

    menu = json.loads(Path("menu.json").read_text(encoding="utf-8"))
    assert C.unit_price(1, "Standard, Vanlig botten", menu) == 130
    assert C.unit_price(1, "Familj, Glutenfri botten", menu) == 350
    assert C.unit_price(1, "standard, extra ost", menu) == 145
    assert C.unit_price(54, "Pommes", menu) == 155
