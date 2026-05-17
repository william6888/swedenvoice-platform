"""
Order Integrity – pure functions för canonical payload, idempotency key, payload hash
och strikt orderdatavalidering. Inga sidoeffekter och inga externa beroenden förutom
stdlib + pydantic, så detta kan testas helt isolerat (CI utan Supabase/Vapi).

Designprinciper:
  * Canonical payload är deterministisk: samma logiska order ger alltid samma hash.
  * Idempotency key bygger primärt på (restaurant_uuid, vapi_call_id, vapi_tool_call_id).
  * Validering är hård: en order som inte är säker att laga får aldrig nå köket.
  * Vid id/name-mismatch returnerar matchen ett tydligt fel som Vapi kan fråga om.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


VALIDATION_VERSION = "phase1"

# Affärsgränser – konservativa för pizzeria-kontext.
MAX_QUANTITY_PER_ITEM = 50
MAX_ITEMS_PER_ORDER = 30
MAX_SPECIAL_REQUEST_LEN = 500
MAX_TOTAL_PRICE = 50000  # SEK; orimligt högre = troligen fel.

ALLOWED_ORDER_STATUSES = ("pending", "needs_review", "ready", "completed", "cancelled", "failed")


@dataclass
class ValidationError(Exception):
    """Kastas när en order inte ska accepteras. error_code är stabilt för UI/loggar."""

    error_code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.error_code}] {self.message}"


@dataclass
class CanonicalItem:
    item_id: int
    name: str
    quantity: int
    price: Optional[float]
    special_requests: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": int(self.item_id),
            "name": self.name,
            "quantity": int(self.quantity),
        }
        if self.price is not None:
            out["price"] = float(self.price)
        if self.special_requests:
            out["special_requests"] = self.special_requests
        return out


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _trim_text(value: Any, max_len: int) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > max_len:
        text = text[:max_len].rstrip()
    return text


def validate_raw_items(items: Any) -> None:
    """
    Säkerställ att raw items från Vapi (innan menymatchning) inte är trasiga.
    Vi vill upptäcka grova fel så tidigt som möjligt och inte hamna i menymatchning
    med strunt-payloads.
    """
    if not isinstance(items, list) or len(items) == 0:
        raise ValidationError("EMPTY_ORDER", "Beställningen innehåller inga artiklar.")
    if len(items) > MAX_ITEMS_PER_ORDER:
        raise ValidationError(
            "TOO_MANY_ITEMS",
            "Beställningen är för stor.",
            {"count": len(items), "max": MAX_ITEMS_PER_ORDER},
        )
    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise ValidationError(
                "ITEM_NOT_OBJECT",
                "En av artiklarna har felaktigt format.",
                {"index": idx},
            )
        qty = _coerce_int(raw.get("quantity") or raw.get("qty"))
        if qty is None or qty < 1:
            raise ValidationError(
                "INVALID_QUANTITY",
                "Antalet måste vara minst 1.",
                {"index": idx, "value": raw.get("quantity")},
            )
        if qty > MAX_QUANTITY_PER_ITEM:
            raise ValidationError(
                "QUANTITY_TOO_HIGH",
                "Antalet är orimligt högt – behöver mänsklig granskning.",
                {"index": idx, "value": qty, "max": MAX_QUANTITY_PER_ITEM},
            )
        sr = raw.get("special_requests") or raw.get("specialRequests") or ""
        if sr and len(str(sr)) > MAX_SPECIAL_REQUEST_LEN:
            raise ValidationError(
                "SPECIAL_REQUEST_TOO_LONG",
                "Specialinstruktionen är för lång.",
                {"index": idx, "max": MAX_SPECIAL_REQUEST_LEN},
            )


def validate_id_name_consistency(
    raw_item: Dict[str, Any],
    canonical_id: Optional[int],
    canonical_name: Optional[str],
) -> None:
    """
    Om både `id` och `name` finns i raw_item måste de peka på samma menyartikel
    (canonical_id/canonical_name). Annars är det en LLM/STT-driven inkonsekvens
    och vi ska aldrig gissa.
    """
    sent_id = raw_item.get("id") if "id" in raw_item else raw_item.get("itemId")
    sent_name = raw_item.get("name")
    if sent_id is None or sent_name is None or canonical_id is None or canonical_name is None:
        return
    sent_id_int = _coerce_int(sent_id)
    if sent_id_int is None:
        return
    sent_name_norm = re.sub(r"\s+", " ", str(sent_name).strip().lower())
    canonical_norm = re.sub(r"\s+", " ", str(canonical_name).strip().lower())
    if not sent_name_norm:
        return
    sent_collapsed = sent_name_norm.replace(" ", "")
    canonical_collapsed = canonical_norm.replace(" ", "")
    name_matches = (
        sent_name_norm == canonical_norm
        or sent_name_norm in canonical_norm
        or canonical_norm in sent_name_norm
        or sent_collapsed in canonical_collapsed
        or canonical_collapsed in sent_collapsed
    )
    id_matches = sent_id_int == int(canonical_id)
    if id_matches and name_matches:
        return
    if not name_matches:
        raise ValidationError(
            "ID_NAME_MISMATCH",
            "id och name pekar på olika menyartiklar.",
            {
                "sent_id": sent_id_int,
                "sent_name": str(sent_name),
                "canonical_id": int(canonical_id),
                "canonical_name": str(canonical_name),
            },
        )


def build_canonical_payload(
    restaurant_uuid: Optional[str],
    canonical_items: List[CanonicalItem],
    order_special_requests: str = "",
) -> Dict[str, Any]:
    """
    Deterministisk canonical representation.
    Innehåller INTE timestamps, random ids eller fältordning – så samma logiska
    beställning ger alltid samma hash.
    """
    items_sorted = sorted(
        (item.to_dict() for item in canonical_items),
        key=lambda x: (int(x["id"]), x.get("name", ""), x.get("special_requests", "")),
    )
    return {
        "restaurant_uuid": restaurant_uuid or "",
        "items": items_sorted,
        "special_requests": (order_special_requests or "").strip(),
        "validation_version": VALIDATION_VERSION,
    }


def build_payload_hash(canonical_payload: Dict[str, Any]) -> str:
    """SHA-256 över canonical payload – stabil mellan retries och processer."""
    raw = json.dumps(canonical_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_idempotency_key(
    restaurant_uuid: Optional[str],
    vapi_call_id: Optional[str],
    vapi_tool_call_id: Optional[str],
    payload_hash: str,
) -> str:
    """
    Primär nyckel: restaurant_uuid:vapi_call_id:vapi_tool_call_id.
    Fallback: restaurant_uuid:vapi_call_id:payload_hash.
    Sista fallback: restaurant_uuid:direct:payload_hash.
    """
    rest = (restaurant_uuid or "noresturant").strip()
    call = (vapi_call_id or "").strip()
    tool = (vapi_tool_call_id or "").strip()
    if call and tool:
        return f"{rest}:{call}:{tool}"
    if call:
        return f"{rest}:{call}:{payload_hash}"
    return f"{rest}:direct:{payload_hash}"


def safe_total_price(items: List[CanonicalItem]) -> float:
    """Räkna totalpris från canonical items. Returnerar float, aldrig NaN/inf."""
    total = 0.0
    for item in items:
        if item.price is None:
            continue
        total += float(item.price) * int(item.quantity)
    if total < 0 or total > MAX_TOTAL_PRICE:
        raise ValidationError(
            "TOTAL_PRICE_OUT_OF_RANGE",
            "Totalpriset är orimligt – behöver mänsklig granskning.",
            {"total": total, "max": MAX_TOTAL_PRICE},
        )
    return round(total, 2)


def normalize_status(value: Optional[str]) -> str:
    """Mappa olika UI/AI-status till backendens enum. Default = pending."""
    v = (value or "").strip().lower()
    if v in ALLOWED_ORDER_STATUSES:
        return v
    if v in ("nya", "ny", "new"):
        return "pending"
    if v in ("redo", "ready_to_pickup", "done"):
        return "ready"
    if v in ("klar", "complete"):
        return "completed"
    if v in ("review", "needs_review", "behover_granskning", "behovsgranska"):
        return "needs_review"
    if v in ("cancel", "cancelled", "avbruten"):
        return "cancelled"
    return "pending"


def assert_status_allowed(value: str) -> str:
    """Raisar ValidationError om status inte är tillåten."""
    norm = normalize_status(value)
    if norm not in ALLOWED_ORDER_STATUSES:  # pragma: no cover - normalize garanterar
        raise ValidationError("INVALID_STATUS", "Otillåten orderstatus.", {"value": value})
    return norm


def make_canonical_items_from_resolved(resolved: List[Dict[str, Any]]) -> List[CanonicalItem]:
    """
    Bygg CanonicalItem-lista från menu_match.resolve_order_items output.
    Förutsätter att menymatchningen redan kört och att id/name är canonical.
    """
    out: List[CanonicalItem] = []
    for row in resolved:
        if not isinstance(row, dict):
            continue
        item_id = _coerce_int(row.get("id"))
        if item_id is None:
            continue
        qty = _coerce_int(row.get("quantity")) or 1
        if qty < 1:
            qty = 1
        if qty > MAX_QUANTITY_PER_ITEM:
            qty = MAX_QUANTITY_PER_ITEM
        name = str(row.get("name") or "").strip() or f"Artikel {item_id}"
        price = row.get("price")
        try:
            price_f = float(price) if price is not None else None
        except (TypeError, ValueError):
            price_f = None
        sr = _trim_text(row.get("special_requests"), MAX_SPECIAL_REQUEST_LEN)
        out.append(CanonicalItem(item_id=item_id, name=name, quantity=qty, price=price_f, special_requests=sr))
    return out


def confidence_summary_for_resolved(resolved: List[Dict[str, Any]]) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Returnerar (all_high_confidence, low_confidence_rows).
    Ordrar med fuzzy_auto-rader markeras som låg konfidens → behöver canonical readback.
    Vi använder detta för att tvinga fram orderbekräftelse även när menymatchningen
    säger ok.
    """
    low: List[Dict[str, Any]] = []
    for idx, row in enumerate(resolved):
        if not isinstance(row, dict):
            continue
        match_type = row.get("matchType") or row.get("match_type")
        if match_type == "fuzzy_auto":
            low.append({"index": idx, "name": row.get("name"), "match_type": match_type})
    return (len(low) == 0, low)
