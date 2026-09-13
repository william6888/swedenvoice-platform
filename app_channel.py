"""Publik kundapp: SMS-kod, öppettider och meny utan att lita på klienten."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

STOCKHOLM = ZoneInfo("Europe/Stockholm")

# Mån=0 … Sön=6. (öppnar, stänger) i timmar, stängning exklusiv.
_DEFAULT_HOURS = {
    0: (11, 21),
    1: (11, 21),
    2: (11, 21),
    3: (11, 21),
    4: (11, 22),
    5: (11, 22),
    6: (11, 21),
}

_OTP_TTL_SEC = 5 * 60
_SESSION_TTL_SEC = 20 * 60
_OTP_MAX_ATTEMPTS = 5
_OTP_PER_PHONE = 3
_OTP_PER_IP = 8
_OTP_WINDOW_SEC = 15 * 60
_ORDERS_PER_PHONE = 2
_ORDERS_WINDOW_SEC = 60 * 60

_OTP_STORE: Dict[str, Dict[str, Any]] = {}
_RATE: Dict[str, List[float]] = {}


def _signing_secret() -> bytes:
    secret = (
        os.getenv("DRAFT_SIGNING_SECRET")
        or os.getenv("ENCRYPTION_SECRET")
        or os.getenv("ADMIN_SECRET")
        or "gislegrillen-app-otp-dev-rotate-me"
    )
    return secret.encode("utf-8")


def swedish_mobile(value: Any) -> Optional[str]:
    """Bara svensk mobil. 070… / +4670… → +4670xxxxxxx."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    cleaned = re.sub(r"[^\d+]", "", raw)
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    digits = re.sub(r"\D", "", cleaned)
    if digits.startswith("0") and len(digits) == 10 and digits[1] == "7":
        digits = "46" + digits[1:]
    if digits.startswith("46") and len(digits) == 11 and digits[2] == "7":
        return "+" + digits
    return None


def restaurant_is_open(now: Optional[datetime] = None) -> bool:
    current = now.astimezone(STOCKHOLM) if now else datetime.now(STOCKHOLM)
    hours = _DEFAULT_HOURS.get(current.weekday())
    if not hours:
        return False
    start, end = hours
    return start <= current.hour < end


def opening_hours_label() -> str:
    return "Mån–tors 11–21, fre–lör 11–22, sön 11–21"


def public_menu(menu: dict) -> dict:
    """Meny till appen: inga alias/id-kartor som inte behövs, behåll id+namn+beskrivning."""
    out: Dict[str, list] = {}
    for key, items in (menu or {}).items():
        if key.startswith("_") or not isinstance(items, list):
            continue
        rows = []
        for it in items:
            if not isinstance(it, dict) or not it.get("name"):
                continue
            rows.append({
                "id": it.get("id"),
                "name": it["name"],
                "description": it.get("description") or "",
            })
        if rows:
            out[key] = rows
    return out


def _prune_rate(key: str, window: float, now: float) -> None:
    hits = [t for t in _RATE.get(key, []) if now - t < window]
    if hits:
        _RATE[key] = hits
    else:
        _RATE.pop(key, None)


def rate_allow(key: str, limit: int, window: float, now: Optional[float] = None) -> bool:
    n = float(now if now is not None else time.time())
    _prune_rate(key, window, n)
    hits = _RATE.get(key, [])
    if len(hits) >= limit:
        return False
    hits.append(n)
    _RATE[key] = hits
    return True


def record_order_phone(phone: str, now: Optional[float] = None) -> None:
    rate_allow(f"order:{phone}", _ORDERS_PER_PHONE, _ORDERS_WINDOW_SEC, now)


def can_place_order(phone: str, now: Optional[float] = None) -> bool:
    n = float(now if now is not None else time.time())
    key = f"order:{phone}"
    _prune_rate(key, _ORDERS_WINDOW_SEC, n)
    return len(_RATE.get(key, [])) < _ORDERS_PER_PHONE


CATEGORY_LABELS = {
    "pizzas": "Pizzor",
    "kebabs": "Kebab",
    "kyckling": "Kyckling",
    "sallader": "Sallad",
    "ovrigt": "Övrigt",
    "lchf": "LCHF",
    "schnitzel": "Schnitzel",
    "hamburgare": "Hamburgare",
    "korv": "Korv",
    "tillbehor": "Tillbehör",
    "drycker": "Dryck",
}


def public_modifiers(menu: dict) -> dict:
    meta = (menu or {}).get("_meta") if isinstance(menu, dict) else {}
    if not isinstance(meta, dict):
        meta = {}
    groups: Dict[str, Any] = {}
    raw_groups = meta.get("modifiers") or {}
    if isinstance(raw_groups, dict):
        for key, vals in raw_groups.items():
            if isinstance(vals, list):
                groups[str(key)] = {"options": [str(v) for v in vals if str(v).strip()]}
            elif isinstance(vals, dict):
                groups[str(key)] = vals
    return {
        "included": meta.get("included") or {},
        "modifiers": groups,
        "gluten": meta.get("gluten") or {},
        "service_options": meta.get("service_options") or ["Ta med", "Äta här"],
    }


def compose_special_requests(service_mode: str, notes: Optional[str]) -> str:
    mode = (service_mode or "").strip().casefold()
    if mode in {"eat_in", "ata_har", "äta här", "dine_in", "dine-in"}:
        label = "Äta här"
    else:
        label = "Ta med"
    extra = (notes or "").strip()
    if extra:
        return f"{label}. {extra}"[:500]
    return label


def sanitize_client_request_id(value: Any) -> Optional[str]:
    raw = re.sub(r"[^A-Za-z0-9_-]", "", str(value or ""))
    return raw[:64] or None


def hash_otp(code: str) -> str:
    return hmac.new(_signing_secret(), str(code).strip().encode("utf-8"), hashlib.sha256).hexdigest()


def session_from_headers(authorization: str, x_app_session: str, now: Optional[float] = None) -> Optional[str]:
    token = ""
    auth = (authorization or "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    token = token or (x_app_session or "").strip()
    return verify_session(token, now)


def request_otp(phone: str, ip: str, now: Optional[float] = None) -> Tuple[bool, str, Optional[str]]:
    """Returnerar (ok, error_sv, code_or_none). Koden är bara till för tester/SMS-sändare."""
    n = float(now if now is not None else time.time())
    if not rate_allow(f"otp-phone:{phone}", _OTP_PER_PHONE, _OTP_WINDOW_SEC, n):
        return (False, "För många koder till det numret. Vänta en stund.", None)
    if ip and not rate_allow(f"otp-ip:{ip}", _OTP_PER_IP, _OTP_WINDOW_SEC, n):
        return (False, "För många försök. Vänta en stund.", None)
    code = f"{secrets.randbelow(1_000_000):06d}"
    _OTP_STORE[phone] = {
        "hash": hash_otp(code),
        "expires": n + _OTP_TTL_SEC,
        "attempts": 0,
    }
    return (True, "", code)


def verify_otp(phone: str, code: str, now: Optional[float] = None) -> Tuple[bool, str]:
    n = float(now if now is not None else time.time())
    row = _OTP_STORE.get(phone)
    if not row:
        return (False, "Ingen kod skickad till det numret.")
    if n > float(row["expires"]):
        _OTP_STORE.pop(phone, None)
        return (False, "Koden har gått ut. Be om en ny.")
    row["attempts"] = int(row.get("attempts") or 0) + 1
    if row["attempts"] > _OTP_MAX_ATTEMPTS:
        _OTP_STORE.pop(phone, None)
        return (False, "För många felaktiga koder. Be om en ny.")
    if not hmac.compare_digest(row["hash"], hash_otp(str(code).strip())):
        return (False, "Fel kod.")
    _OTP_STORE.pop(phone, None)
    return (True, "")


def issue_session(phone: str, now: Optional[float] = None) -> str:
    n = int(now if now is not None else time.time())
    exp = n + _SESSION_TTL_SEC
    body = f"{phone}|{exp}"
    sig = hmac.new(_signing_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}|{sig}"


def verify_session(token: str, now: Optional[float] = None) -> Optional[str]:
    if not token or token.count("|") != 2:
        return None
    phone, exp_s, sig = token.split("|", 2)
    body = f"{phone}|{exp_s}"
    expected = hmac.new(_signing_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        exp = int(exp_s)
    except ValueError:
        return None
    if float(now if now is not None else time.time()) > exp:
        return None
    if not swedish_mobile(phone):
        return None
    return phone


def otp_sms_text(code: str) -> str:
    return f"Din kod till Gislegrillen är {code}. Gäller i fem minuter."


def send_plain_sms(to: str, text: str, sender: Optional[Callable[[str, str], bool]] = None) -> bool:
    if sender:
        return bool(sender(to, text))
    return False


def reset_stores() -> None:
    _OTP_STORE.clear()
    _RATE.clear()
