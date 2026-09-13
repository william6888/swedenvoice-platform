"""
Confirmation – signerade draft-tokens för canonical readback innan commit.

Mål:
  * AI får aldrig lova kunden pickup-tid förrän servern bekräftat ordern.
  * Servern svarar på draft_order med canonical items, pris och en signerad token.
  * place_order kan kräva en draft_token. Servern verifierar att hashen i token
    matchar vad som faktiskt skickas in – annars ber vi AI läsa upp på nytt.

Tokenen är HMAC-signerad så vi behöver inte spara state. Vid behov går det
att flytta till Supabase-stored tokens senare utan att ändra publik kontrakt.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any, Dict, Optional, Tuple


DRAFT_TTL_SECONDS = 300  # 5 minuter – ett samtal hinner aldrig längre.


def _signing_secret() -> bytes:
    secret = (
        os.getenv("DRAFT_SIGNING_SECRET")
        or os.getenv("ENCRYPTION_SECRET")
        or os.getenv("ADMIN_SECRET")
        or "gislegrillen-default-draft-secret-rotate-me"
    )
    return secret.encode("utf-8")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(token: str) -> bytes:
    pad = "=" * (-len(token) % 4)
    return base64.urlsafe_b64decode(token + pad)


def _sign(payload_b64: str) -> str:
    sig = hmac.new(_signing_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64url_encode(sig)


def issue_draft_token(
    *,
    restaurant_uuid: Optional[str],
    payload_hash: str,
    items_summary: list,
    total_price: float,
    needs_human_review: bool,
    issued_at: Optional[float] = None,
    ttl_seconds: int = DRAFT_TTL_SECONDS,
) -> Tuple[str, Dict[str, Any]]:
    """
    Skapa en signerad draft-token. Returnerar (token, payload_dict).
    payload_dict är endast för logg/feedback – AI ska aldrig parse:a token.
    """
    issued = float(issued_at if issued_at is not None else time.time())
    payload = {
        "restaurant_uuid": restaurant_uuid or "",
        "payload_hash": payload_hash,
        "items_summary": items_summary,
        "total_price": float(total_price),
        "needs_human_review": bool(needs_human_review),
        "issued_at": issued,
        "expires_at": issued + max(int(ttl_seconds), 30),
        "version": 1,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    body_b64 = _b64url_encode(raw)
    sig_b64 = _sign(body_b64)
    return f"{body_b64}.{sig_b64}", payload


def verify_draft_token(
    token: str,
    *,
    expected_restaurant_uuid: Optional[str],
    expected_payload_hash: str,
    now: Optional[float] = None,
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Verifiera token. Returnerar (ok, payload, error_code).
    Felkoder: INVALID_FORMAT | INVALID_SIGNATURE | EXPIRED | RESTAURANT_MISMATCH | HASH_MISMATCH.
    """
    if not token or not isinstance(token, str) or "." not in token:
        return (False, None, "INVALID_FORMAT")
    body_b64, sig_b64 = token.rsplit(".", 1)
    expected_sig = _sign(body_b64)
    if not hmac.compare_digest(expected_sig, sig_b64):
        return (False, None, "INVALID_SIGNATURE")
    try:
        raw = _b64url_decode(body_b64)
        payload = json.loads(raw)
    except Exception:
        return (False, None, "INVALID_FORMAT")
    n = float(now if now is not None else time.time())
    if n > float(payload.get("expires_at") or 0):
        return (False, payload, "EXPIRED")
    if expected_restaurant_uuid:
        if (payload.get("restaurant_uuid") or "") != expected_restaurant_uuid:
            return (False, payload, "RESTAURANT_MISMATCH")
    if (payload.get("payload_hash") or "") != expected_payload_hash:
        return (False, payload, "HASH_MISMATCH")
    return (True, payload, None)


_SPEAKABLE_NAME_SUBS = (
    (re.compile(r"\b200g\b", re.IGNORECASE), "tvåhundra gram"),
    (re.compile(r"\b150g\b", re.IGNORECASE), "etthundrafemtio gram"),
    (re.compile(r"\b90g\b", re.IGNORECASE), "nittio gram"),
    (re.compile(r"\b33cl\b", re.IGNORECASE), "trettiotre"),
    (re.compile(r"\b50cl\b", re.IGNORECASE), "femtio"),
    (re.compile(r"\b2\s*liter\b", re.IGNORECASE), "två liter"),
    (re.compile(r"\b1[.,]5\s*liter\b", re.IGNORECASE), "en och en halv liter"),
)


def _speakable_item_name(name: str) -> str:
    """Gör menynamn läsbara i TTS utan att hugga vid g eller cl."""
    out = name
    for pattern, spoken in _SPEAKABLE_NAME_SUBS:
        out = pattern.sub(spoken, out)
    return out


def format_verbal_readback(items: list, special_requests: str = "") -> str:
    """
    Text AI ska läsa upp för kunden – inga priser, inga id-nummer (matchar original-prompt).
    """
    parts: list[str] = []
    for it in items:
        try:
            qty = int(it.get("quantity") or 1)
        except Exception:
            qty = 1
        name = _speakable_item_name(str(it.get("name") or "okänd").strip())
        sr = (it.get("special_requests") or it.get("notes") or "").strip()
        if qty == 1:
            line = f"en {name}"
        elif qty == 2:
            line = f"två {name}"
        elif qty == 3:
            line = f"tre {name}"
        else:
            line = f"{qty} {name}"
        if sr:
            line += f", {sr}"
        parts.append(line)

    if not parts:
        return "ingen beställning"

    if len(parts) == 1:
        text = parts[0]
    else:
        text = ", ".join(parts[:-1]) + " och " + parts[-1]

    order_notes = (special_requests or "").strip()
    normalized = order_notes.casefold().replace("_", " ")
    if normalized.startswith("ta med"):
        order_notes = order_notes[len("ta med"):].lstrip(" .;,:")
    elif normalized.startswith("äta här") or normalized.startswith("ata har"):
        prefix_len = len("äta här") if normalized.startswith("äta här") else len("ata har")
        order_notes = order_notes[prefix_len:].lstrip(" .;,:")

    if order_notes:
        text += f", övrigt {order_notes}"
    # Små bokstäver så TTS inte läser matnamn som frågor.
    return text.lower()


def format_canonical_readback(items: list, total_price: float, special_requests: str = "") -> str:
    """
    Full readback inkl. total (logg/internt). För kundröst: använd format_verbal_readback.
    """
    verbal = format_verbal_readback(items, special_requests)
    if verbal.endswith("."):
        verbal = verbal[:-1]
    return f"{verbal}. Totalt: {round(float(total_price), 2)} kr."
