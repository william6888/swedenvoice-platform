"""
Ops Agent – policy-styrd autonom drift för pizzeria-plattformen.

Detta är medvetet INTE en fri LLM som “fixar saker”. Det är en deterministisk
policy engine som registrerar incidenter, kör en allowlistad uppsättning åtgärder
och eskalerar osäkra fall till människa.

Ansvar:
  * Registrera incidenter med tydlig severity och tenant-scope.
  * Logga varje autonom åtgärd i ops_actions (audit trail).
  * Pausa orderintag för en tenant vid upprepade kritiska fel.
  * Markera order som needs_human_review när något kritiskt är osäkert.
  * Skicka driftalert till operatör (idag log-only, senare Slack/email/SMS).
  * ALDRIG ändra bekräftad order, pris, meny eller säkerhet automatiskt.

Modulen försöker ALDRIG raisa pga DB-fel – ops-systemet får aldrig krascha hot path.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# ====== Allowlistade autonoma åtgärder ======
# Policy: agenten får bara köra dessa actions automatiskt. Allt annat kräver
# manuell trigger.
SAFE_ACTIONS = frozenset(
    {
        "retry_sms",
        "deadletter_sms",
        "invalidate_menu_cache",
        "invalidate_tenant_cache",
        "create_incident",
        "update_incident",
        "pause_tenant_intake",
        "resume_tenant_intake",   # endast efter healthcheck-grön status
        "mark_order_needs_review",
        "alert_operator",
        "reconcile_orders",
    }
)

# ====== Tröskelvärden ======
SUPABASE_FAIL_PAUSE_THRESHOLD = 3
SMS_FAIL_DEADLETTER_AFTER = 5
INTAKE_RESUME_GREEN_PERIOD_SEC = 120


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _safe_table(client: Any, table: str):
    return client.table(table)


def log_action(
    supabase_client: Any,
    *,
    action: str,
    restaurant_uuid: Optional[str],
    restaurant_id: Optional[str],
    incident_id: Optional[str] = None,
    reason: str = "",
    result: str = "ok",
    reversible: bool = True,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Audit-logga en åtgärd. Soft-fail om tabellen saknas (logga och fortsätt)."""
    if action not in SAFE_ACTIONS:
        # Hårt skydd mot programmeringsfel.
        print(f"ops_agent: BLOCKED unsafe action attempt: {action}")
        return
    print(f"ops_agent: action={action} tenant={restaurant_id} reason={reason} result={result}")
    if not supabase_client:
        return
    row = {
        "action": action,
        "restaurant_uuid": restaurant_uuid,
        "restaurant_id": restaurant_id,
        "incident_id": incident_id,
        "reason": reason[:1000],
        "result": result[:200],
        "reversible": bool(reversible),
        "details": details or {},
    }
    try:
        _safe_table(supabase_client, "ops_actions").insert(row).execute()
    except Exception as e:
        print(f"ops_agent: log_action soft-fail: {e}")


def create_incident(
    supabase_client: Any,
    *,
    incident_type: str,
    severity: str,
    summary: str,
    restaurant_uuid: Optional[str] = None,
    restaurant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    vapi_call_id: Optional[str] = None,
    order_id: Optional[str] = None,
    human_required: bool = False,
    details: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Skapa incident. Returnerar incident-id eller None vid fel.
    Severity: P0 (orderintegritet hotad), P1 (drift), P2 (varning), P3/INFO (tracking).
    """
    print(
        f"ops_agent: incident type={incident_type} severity={severity} "
        f"tenant={restaurant_id} call={vapi_call_id} order={order_id} human={human_required}"
    )
    if not supabase_client:
        return None
    row = {
        "type": incident_type[:120],
        "severity": severity if severity in ("P0", "P1", "P2", "P3", "INFO") else "P2",
        "summary": (summary or "")[:1000],
        "restaurant_uuid": restaurant_uuid,
        "restaurant_id": restaurant_id,
        "correlation_id": correlation_id,
        "vapi_call_id": vapi_call_id,
        "order_id": order_id,
        "human_required": bool(human_required),
        "details": details or {},
        "status": "open",
    }
    try:
        resp = _safe_table(supabase_client, "incidents").insert(row).execute()
        data = getattr(resp, "data", None) or []
        if data:
            return str(data[0].get("id") or "") or None
    except Exception as e:
        print(f"ops_agent: create_incident soft-fail: {e}")
    return None


def get_tenant_health(
    supabase_client: Any,
    restaurant_uuid: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not supabase_client or not restaurant_uuid:
        return None
    try:
        resp = (
            _safe_table(supabase_client, "tenant_health")
            .select("*")
            .eq("restaurant_uuid", restaurant_uuid)
            .limit(1)
            .execute()
        )
        data = getattr(resp, "data", None) or []
        return data[0] if data else None
    except Exception as e:
        print(f"ops_agent: get_tenant_health soft-fail: {e}")
        return None


def upsert_tenant_health(
    supabase_client: Any,
    *,
    restaurant_uuid: str,
    restaurant_id: Optional[str],
    intake_status: Optional[str] = None,
    intake_paused_reason: Optional[str] = None,
    last_supabase_ok: Optional[str] = None,
    last_sms_ok: Optional[str] = None,
    last_order_committed: Optional[str] = None,
    consecutive_supabase_failures: Optional[int] = None,
    consecutive_sms_failures: Optional[int] = None,
) -> None:
    if not supabase_client or not restaurant_uuid:
        return
    payload: Dict[str, Any] = {"restaurant_uuid": restaurant_uuid, "updated_at": _now_iso()}
    if restaurant_id is not None:
        payload["restaurant_id"] = restaurant_id
    if intake_status is not None:
        payload["intake_status"] = intake_status
    if intake_paused_reason is not None:
        payload["intake_paused_reason"] = intake_paused_reason
    if last_supabase_ok is not None:
        payload["last_supabase_ok"] = last_supabase_ok
    if last_sms_ok is not None:
        payload["last_sms_ok"] = last_sms_ok
    if last_order_committed is not None:
        payload["last_order_committed"] = last_order_committed
    if consecutive_supabase_failures is not None:
        payload["consecutive_supabase_failures"] = int(consecutive_supabase_failures)
    if consecutive_sms_failures is not None:
        payload["consecutive_sms_failures"] = int(consecutive_sms_failures)
    try:
        _safe_table(supabase_client, "tenant_health").upsert(payload, on_conflict="restaurant_uuid").execute()
    except Exception as e:
        print(f"ops_agent: upsert_tenant_health soft-fail: {e}")


def is_intake_paused(supabase_client: Any, restaurant_uuid: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Kolla om en tenant är pausad. (paused, reason)."""
    health = get_tenant_health(supabase_client, restaurant_uuid)
    if not health:
        return (False, None)
    status = (health.get("intake_status") or "").strip().lower()
    if status == "paused":
        return (True, health.get("intake_paused_reason") or "paused")
    return (False, None)


def record_supabase_failure(
    supabase_client: Any,
    *,
    restaurant_uuid: Optional[str],
    restaurant_id: Optional[str],
    error_message: str,
    correlation_id: Optional[str] = None,
    order_id: Optional[str] = None,
) -> None:
    """
    Räkna upp consecutive_supabase_failures. Pausa intake om tröskel överskrids
    (säker autonom åtgärd – stoppa nya falska bekräftelser).
    """
    if not supabase_client or not restaurant_uuid:
        return
    health = get_tenant_health(supabase_client, restaurant_uuid) or {}
    failures = int(health.get("consecutive_supabase_failures") or 0) + 1
    new_status = health.get("intake_status") or "open"
    paused_reason = health.get("intake_paused_reason") or ""
    if failures >= SUPABASE_FAIL_PAUSE_THRESHOLD and new_status != "paused":
        new_status = "paused"
        paused_reason = "supabase_insert_failures"
        log_action(
            supabase_client,
            action="pause_tenant_intake",
            restaurant_uuid=restaurant_uuid,
            restaurant_id=restaurant_id,
            reason=f"{failures} consecutive supabase failures",
            details={"error": error_message[:300]},
        )
        create_incident(
            supabase_client,
            incident_type="supabase_insert_failed",
            severity="P0",
            summary=f"Tenant intake pausad efter {failures} Supabase-fel.",
            restaurant_uuid=restaurant_uuid,
            restaurant_id=restaurant_id,
            correlation_id=correlation_id,
            order_id=order_id,
            human_required=True,
            details={"error": error_message[:500]},
        )
    upsert_tenant_health(
        supabase_client,
        restaurant_uuid=restaurant_uuid,
        restaurant_id=restaurant_id,
        intake_status=new_status,
        intake_paused_reason=paused_reason,
        consecutive_supabase_failures=failures,
    )


def record_supabase_success(
    supabase_client: Any,
    *,
    restaurant_uuid: Optional[str],
    restaurant_id: Optional[str],
    order_id: Optional[str] = None,
) -> None:
    if not supabase_client or not restaurant_uuid:
        return
    upsert_tenant_health(
        supabase_client,
        restaurant_uuid=restaurant_uuid,
        restaurant_id=restaurant_id,
        last_supabase_ok=_now_iso(),
        last_order_committed=_now_iso() if order_id else None,
        consecutive_supabase_failures=0,
    )


def queue_sms_job(
    supabase_client: Any,
    *,
    restaurant_uuid: Optional[str],
    restaurant_id: Optional[str],
    order_id: Optional[str],
    db_order_id: Optional[str],
    to_number: Optional[str],
    body: str,
) -> Optional[str]:
    """Lägg SMS-jobb i kö så agenten kan retrya utan att hot path blockeras."""
    if not supabase_client:
        return None
    row = {
        "restaurant_uuid": restaurant_uuid,
        "restaurant_id": restaurant_id,
        "order_id": order_id,
        "db_order_id": db_order_id,
        "to_number": to_number or "",
        "body": body[:1500],
        "status": "missing_phone" if not to_number else "pending",
        "max_attempts": 3,
        "next_attempt_at": _now_iso(),
    }
    try:
        resp = _safe_table(supabase_client, "sms_jobs").insert(row).execute()
        data = getattr(resp, "data", None) or []
        return str(data[0].get("id") or "") if data else None
    except Exception as e:
        print(f"ops_agent: queue_sms_job soft-fail: {e}")
        return None


def alert_operator(
    supabase_client: Any,
    *,
    severity: str,
    title: str,
    body: str,
    restaurant_uuid: Optional[str] = None,
    restaurant_id: Optional[str] = None,
) -> None:
    """
    Skicka alert. Idag: log-only + audit. I framtiden: Slack/email/SMS via
    konfigurerade kanaler. Designat så att kanal kan bytas utan att rör hot path.
    """
    print(f"ops_agent: ALERT severity={severity} title={title}")
    log_action(
        supabase_client,
        action="alert_operator",
        restaurant_uuid=restaurant_uuid,
        restaurant_id=restaurant_id,
        reason=title,
        details={"severity": severity, "body": body[:1000]},
    )


def safe_resume_tenant_intake(
    supabase_client: Any,
    *,
    restaurant_uuid: str,
    restaurant_id: Optional[str],
    actor: str = "human",
) -> Tuple[bool, str]:
    """
    Återaktivera orderintag för en tenant. ENDAST efter att Supabase fungerat
    grönt under en period eller efter manuell trigger. Vi tillåter "human" som
    actor – agenten själv ska normalt inte återöppna säkerhetsrelaterade pauser.
    """
    if not supabase_client or not restaurant_uuid:
        return (False, "no_client")
    health = get_tenant_health(supabase_client, restaurant_uuid)
    if not health:
        return (False, "tenant_unknown")
    if (health.get("intake_status") or "").lower() != "paused":
        return (True, "already_open")
    if actor != "human":
        last_ok = health.get("last_supabase_ok")
        if not last_ok:
            return (False, "no_green_period")
    upsert_tenant_health(
        supabase_client,
        restaurant_uuid=restaurant_uuid,
        restaurant_id=restaurant_id,
        intake_status="open",
        intake_paused_reason="",
    )
    log_action(
        supabase_client,
        action="resume_tenant_intake",
        restaurant_uuid=restaurant_uuid,
        restaurant_id=restaurant_id,
        reason=f"resumed by {actor}",
        details={"actor": actor},
    )
    return (True, "resumed")
