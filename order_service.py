"""
Order Service – Supabase som system of record för ordrar, idempotency och audit.

Designprinciper:
  * Hot path skriver Supabase först. Lyckas inte commit:en så finns ingen order.
  * Idempotency-records hindrar dubbletter vid Vapi/Railway retries.
  * order_events skrivs append-only för spårning.
  * orders.json kan fortfarande skrivas som lokal debug-spegel, men är aldrig
    sanning för Lovable/KDS.
  * Om migrationen inte är körd (saknar idempotency_records eller order_events)
    fungerar systemet ändå (degraded mode), men ops-agenten ska skapa incident.

Ingen av dessa funktioner får raisa pga DB-schema-glitch som inte är vårt fel.
Viktigt orderbeslut → False/None med tydlig logg, så hot path kan returnera
success:false och ingen falsk bekräftelse skickas till kunden.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class OrderCommitResult:
    success: bool
    order_id: Optional[str]
    db_order_id: Optional[str]
    idempotent_replay: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    response_payload: Optional[Dict[str, Any]] = None


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _is_missing_table_error(err: Any) -> bool:
    text = str(err or "").lower()
    return (
        "does not exist" in text
        or "undefined_table" in text
        or "relation" in text
        and "does not exist" in text
    ) or "not found" in text


def _is_missing_column_error(err: Any) -> bool:
    text = str(err or "").lower()
    return (
        "undefined_column" in text
        or ("column" in text and "does not exist" in text)
    )


def lookup_existing_idempotency(
    supabase_client: Any,
    idempotency_key: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Slå upp existerande idempotency-rad. Returnerar (row, error_text).
    Om migrationen saknas returneras (None, "missing_table"). Hot path tolererar då
    detta men loggar varning och fortsätter utan persistent skydd.
    """
    if not supabase_client or not idempotency_key:
        return (None, None)
    try:
        resp = supabase_client.table("idempotency_records").select("*").eq("key", idempotency_key).limit(1).execute()
        data = getattr(resp, "data", None) or []
        if data:
            return (data[0], None)
        return (None, None)
    except Exception as e:
        if _is_missing_table_error(e):
            return (None, "missing_table")
        return (None, str(e))


def lookup_completed_for_call(
    supabase_client: Any,
    vapi_call_id: Optional[str],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Hitta senaste completed idempotency-rad för ett Vapi-samtal.

    Skydd mot dubbel-place_order per samtal: om AI ringer place_order två gånger
    (olika tool_call_id) under samma samtal vill vi inte committa två gånger.
    Returnera den första completed-raden så vi kan replay:a den.
    """
    if not supabase_client or not vapi_call_id:
        return (None, None)
    try:
        resp = (
            supabase_client.table("idempotency_records")
            .select("*")
            .eq("vapi_call_id", vapi_call_id)
            .eq("status", "completed")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        data = getattr(resp, "data", None) or []
        if data:
            return (data[0], None)
        return (None, None)
    except Exception as e:
        if _is_missing_table_error(e):
            return (None, "missing_table")
        return (None, str(e))


def reserve_idempotency(
    supabase_client: Any,
    idempotency_key: str,
    restaurant_uuid: Optional[str],
    restaurant_id: Optional[str],
    vapi_call_id: Optional[str],
    vapi_tool_call_id: Optional[str],
    payload_hash: str,
) -> Tuple[bool, Optional[str]]:
    """
    Försök reservera idempotency-nyckeln med status='processing'.
    Returnerar (reserved, error_text).
    * reserved=True  → vi äger denna order, fortsätt commit.
    * reserved=False, error="duplicate" → någon annan har redan reserverat.
    * reserved=False, error="missing_table" → tabellen finns inte (degraded).
    """
    if not supabase_client or not idempotency_key:
        return (False, "no_client")
    row = {
        "key": idempotency_key,
        "restaurant_uuid": restaurant_uuid,
        "restaurant_id": restaurant_id,
        "vapi_call_id": vapi_call_id,
        "vapi_tool_call_id": vapi_tool_call_id,
        "payload_hash": payload_hash,
        "status": "processing",
        "updated_at": _now_iso(),
    }
    try:
        supabase_client.table("idempotency_records").insert(row).execute()
        return (True, None)
    except Exception as e:
        if _is_missing_table_error(e):
            return (False, "missing_table")
        text = str(e).lower()
        if "duplicate" in text or "23505" in text or "unique" in text:
            return (False, "duplicate")
        return (False, str(e))


def complete_idempotency(
    supabase_client: Any,
    idempotency_key: str,
    order_id: str,
    db_order_id: Optional[str],
    response_payload: Dict[str, Any],
) -> None:
    if not supabase_client or not idempotency_key:
        return
    patch = {
        "status": "completed",
        "order_id": order_id,
        "db_order_id": db_order_id,
        "response": response_payload,
        "updated_at": _now_iso(),
    }
    try:
        supabase_client.table("idempotency_records").update(patch).eq("key", idempotency_key).execute()
    except Exception as e:
        print(f"order_service: complete_idempotency soft-fail: {e}")


def fail_idempotency(
    supabase_client: Any,
    idempotency_key: str,
    error_message: str,
) -> None:
    if not supabase_client or not idempotency_key:
        return
    try:
        supabase_client.table("idempotency_records").update(
            {"status": "failed", "error": error_message[:500], "updated_at": _now_iso()}
        ).eq("key", idempotency_key).execute()
    except Exception as e:
        print(f"order_service: fail_idempotency soft-fail: {e}")


def insert_order_row(
    supabase_client: Any,
    row: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str]]:
    """
    Insert en order-rad. Returnerar (db_id, error_text).
    Vid kolumnfel försöker vi förenkla raden (bakåtkompatibelt med äldre schema).
    """
    if not supabase_client:
        return (None, "no_client")

    full_row = dict(row)
    try:
        resp = supabase_client.table("orders").insert(full_row).execute()
        err = getattr(resp, "error", None)
        if err:
            raise RuntimeError(str(err))
        data = getattr(resp, "data", None) or []
        if not data:
            return (None, "rls_or_empty")
        return (str(data[0].get("id") or "") or None, None)
    except Exception as e:
        if not _is_missing_column_error(e):
            return (None, str(e))

    # Försök två: ta bort kolumner som migrationen kanske inte kört.
    fallback = dict(row)
    for col in (
        "vapi_call_id",
        "vapi_tool_call_id",
        "idempotency_key",
        "payload_hash",
        "validation_version",
        "needs_human_review",
        "confirmation_token",
        "source",
        "special_instructions",
        "order_id",
        "sms_status",
        "sms_to",
    ):
        fallback.pop(col, None)
    try:
        resp = supabase_client.table("orders").insert(fallback).execute()
        err = getattr(resp, "error", None)
        if err:
            raise RuntimeError(str(err))
        data = getattr(resp, "data", None) or []
        if not data:
            return (None, "rls_or_empty_fallback")
        return (str(data[0].get("id") or "") or None, None)
    except Exception as e2:
        return (None, str(e2))


def write_order_event(
    supabase_client: Any,
    *,
    event_type: str,
    restaurant_uuid: Optional[str],
    restaurant_id: Optional[str],
    order_id: Optional[str],
    correlation_id: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Append en order_event. Soft-fail om tabellen saknas eller fel uppstår –
    audit-logg får aldrig blockera orderkedjan.
    """
    if not supabase_client:
        return
    row = {
        "event_type": event_type,
        "restaurant_uuid": restaurant_uuid,
        "restaurant_id": restaurant_id,
        "order_id": order_id,
        "correlation_id": correlation_id,
        "payload": payload or {},
    }
    try:
        supabase_client.table("order_events").insert(row).execute()
    except Exception as e:
        print(f"order_service: write_order_event soft-fail event={event_type}: {e}")


def fetch_orders(
    supabase_client: Any,
    *,
    restaurant_uuid: Optional[str] = None,
    restaurant_id: Optional[str] = None,
    limit: int = 200,
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    Hämta ordrar för en tenant. Returnerar (rows, error_text).
    Tenant-scope: endast ordrar för restaurant_uuid eller restaurant_id.
    Vi använder bara service_role från backend så RLS påverkar inte oss.
    """
    if not supabase_client:
        return (None, "no_client")
    try:
        q = supabase_client.table("orders").select(
            "id, order_id, status, items, total_price, special_instructions, customer_name, customer_phone, created_at, restaurant_id, restaurant_uuid, needs_human_review"
        )
        if restaurant_uuid:
            q = q.eq("restaurant_uuid", restaurant_uuid)
        elif restaurant_id:
            q = q.eq("restaurant_id", restaurant_id)
        resp = q.order("created_at", desc=True).limit(int(limit)).execute()
        data = getattr(resp, "data", None) or []
        return (data, None)
    except Exception as e:
        if _is_missing_column_error(e):
            try:
                q = supabase_client.table("orders").select("*")
                if restaurant_uuid:
                    q = q.eq("restaurant_uuid", restaurant_uuid)
                elif restaurant_id:
                    q = q.eq("restaurant_id", restaurant_id)
                resp = q.order("created_at", desc=True).limit(int(limit)).execute()
                data = getattr(resp, "data", None) or []
                return (data, None)
            except Exception as e2:
                return (None, str(e2))
        return (None, str(e))


def update_order_status(
    supabase_client: Any,
    *,
    order_id: str,
    new_status: str,
    restaurant_uuid: Optional[str] = None,
    restaurant_id: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Uppdatera orderstatus i Supabase. Tenant-scope krävs så vi inte råkar
    uppdatera fel restaurangs order.
    """
    if not supabase_client:
        return (False, "no_client")
    try:
        q = supabase_client.table("orders").update({"status": new_status}).eq("order_id", order_id)
        if restaurant_uuid:
            q = q.eq("restaurant_uuid", restaurant_uuid)
        elif restaurant_id:
            q = q.eq("restaurant_id", restaurant_id)
        resp = q.execute()
        data = getattr(resp, "data", None)
        if not isinstance(data, list) or len(data) == 0:
            return (False, "not_found_or_rls")
        return (True, None)
    except Exception as e:
        return (False, str(e))


def shape_order_for_dashboard(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mappa Supabase-rad till samma shape som index.html förväntar sig:
    { order_id, items, total_price, status, special_requests, timestamp }
    """
    items = row.get("items") or []
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except Exception:
            items = []
    norm_items: List[Dict[str, Any]] = []
    if isinstance(items, list):
        for it in items:
            if not isinstance(it, dict):
                continue
            norm_items.append(
                {
                    "id": it.get("id"),
                    "name": it.get("name") or "",
                    "quantity": int(it.get("quantity") or 0),
                    "price": it.get("price"),
                    "special_requests": it.get("notes") or it.get("special_requests") or "",
                }
            )
    timestamp = row.get("created_at") or ""
    return {
        "order_id": row.get("order_id") or row.get("id") or "",
        "items": norm_items,
        "total_price": float(row.get("total_price") or 0),
        "status": (row.get("status") or "pending").strip().lower(),
        "special_requests": row.get("special_instructions") or "",
        "timestamp": timestamp,
        "needs_human_review": bool(row.get("needs_human_review") or False),
        "restaurant_id": row.get("restaurant_id") or "",
        "restaurant_uuid": row.get("restaurant_uuid") or "",
    }
