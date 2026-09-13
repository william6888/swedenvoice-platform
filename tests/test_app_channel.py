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
    assert public["pizzas"][0] == {"id": 1, "name": "Margherita", "description": "Ost"}
    assert "aliases" not in public["pizzas"][0]
    mods = C.public_modifiers({
        "_meta": {"modifiers": {"saser": ["Mild", "Stark"]}},
    })
    assert mods["modifiers"]["saser"]["options"] == ["Mild", "Stark"]
