"""
Ops Worker – periodisk autonom drift som agerar inom policy.

Workflow:
  * process_sms_jobs: retrya pending SMS-jobb, dead-letter efter max_attempts.
  * reconcile_tenant_health: auto-resume tenants där supabase varit grön länge nog.
  * cleanup_idempotency: rensa gamla completed/failed idempotency-rader.

Designprinciper:
  * En "tick" är idempotent. Att köra två ticks i rad parallellt får inte ge
    dubbla SMS eller felaktiga resumes. Vi använder Supabase update WHERE status=
    för att sätta sending och kan lugnt köras från Railway cron eller manuellt.
  * SMS-sändaren injiceras (sms_sender) så hot path inte kopplas hårt till
    Vonage – samma worker funkar i tester.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import ops_agent


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _from_iso(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except Exception:
        return None


def _next_backoff_seconds(attempts: int) -> int:
    # 30s, 2 min, 10 min, 30 min, 60 min – sedan dead-letter.
    schedule = [30, 120, 600, 1800, 3600]
    if attempts <= 0:
        return schedule[0]
    if attempts - 1 < len(schedule):
        return schedule[attempts - 1]
    return schedule[-1]


def process_sms_jobs(
    supabase_client: Any,
    *,
    sms_sender: Optional[Callable[[str, str], Dict[str, Any]]] = None,
    batch_size: int = 20,
) -> Dict[str, Any]:
    """
    Plocka upp pending sms_jobs och försök skicka. Soft-fail om sms_jobs saknas.
    sms_sender(to_number, body) → {ok: bool, message_id?: str, error?: str}.
    """
    summary = {"picked": 0, "sent": 0, "failed": 0, "dead_letter": 0, "missing_phone": 0}
    if not supabase_client:
        return summary

    try:
        resp = (
            supabase_client.table("sms_jobs")
            .select("*")
            .eq("status", "pending")
            .lte("next_attempt_at", _now_iso())
            .order("next_attempt_at", desc=False)
            .limit(int(batch_size))
            .execute()
        )
        rows: List[Dict[str, Any]] = getattr(resp, "data", None) or []
    except Exception as e:
        print(f"ops_worker: process_sms_jobs select fail: {e}")
        return summary

    summary["picked"] = len(rows)
    for row in rows:
        job_id = row.get("id")
        to_number = row.get("to_number") or ""
        body = row.get("body") or ""
        attempts = int(row.get("attempts") or 0)
        max_attempts = int(row.get("max_attempts") or 3)
        restaurant_uuid = row.get("restaurant_uuid")
        restaurant_id = row.get("restaurant_id")
        if not to_number:
            try:
                supabase_client.table("sms_jobs").update(
                    {"status": "missing_phone", "updated_at": _now_iso()}
                ).eq("id", job_id).execute()
                summary["missing_phone"] += 1
            except Exception as e:
                print(f"ops_worker: missing_phone update fail: {e}")
            continue

        # Markera "sending" så två workers inte plockar samma jobb.
        # VIKTIGT: verifiera att UPDATE:n faktiskt träffade raden. Om en annan
        # tick (t.ex. /admin/ops/run parallellt med bakgrundsloopen) redan låst
        # jobbet matchar WHERE status='pending' 0 rader – då får vi INTE skicka,
        # annars dubbla SMS till kunden.
        try:
            lock_resp = supabase_client.table("sms_jobs").update(
                {"status": "sending", "attempts": attempts + 1, "updated_at": _now_iso()}
            ).eq("id", job_id).eq("status", "pending").execute()
            lock_rows = getattr(lock_resp, "data", None)
            if isinstance(lock_rows, list) and len(lock_rows) == 0:
                print(f"ops_worker: sms_job {job_id} redan låst av annan tick – hoppar över")
                continue
        except Exception as e:
            print(f"ops_worker: lock sms_job fail: {e}")
            continue

        result: Dict[str, Any]
        if sms_sender is None:
            result = {"ok": False, "error": "no_sender_configured"}
        else:
            try:
                result = sms_sender(to_number, body) or {"ok": False, "error": "no_result"}
            except Exception as e:
                result = {"ok": False, "error": str(e)[:200]}

        if result.get("ok"):
            try:
                supabase_client.table("sms_jobs").update(
                    {"status": "sent", "updated_at": _now_iso(), "last_error": ""}
                ).eq("id", job_id).execute()
                ops_agent.log_action(
                    supabase_client,
                    action="retry_sms",
                    restaurant_uuid=restaurant_uuid,
                    restaurant_id=restaurant_id,
                    reason="sms sent ok",
                    details={"job_id": str(job_id), "attempts": attempts + 1},
                )
                ops_agent.upsert_tenant_health(
                    supabase_client,
                    restaurant_uuid=restaurant_uuid or "",
                    restaurant_id=restaurant_id,
                    last_sms_ok=_now_iso(),
                    consecutive_sms_failures=0,
                )
                summary["sent"] += 1
            except Exception as e:
                print(f"ops_worker: mark sent fail: {e}")
            continue

        # Misslyckad försökning: backoff eller dead-letter.
        new_attempts = attempts + 1
        if new_attempts >= max_attempts:
            try:
                supabase_client.table("sms_jobs").update(
                    {
                        "status": "dead_letter",
                        "updated_at": _now_iso(),
                        "last_error": str(result.get("error") or "")[:300],
                    }
                ).eq("id", job_id).execute()
                ops_agent.log_action(
                    supabase_client,
                    action="deadletter_sms",
                    restaurant_uuid=restaurant_uuid,
                    restaurant_id=restaurant_id,
                    reason="sms max attempts",
                    details={"job_id": str(job_id), "attempts": new_attempts},
                )
                ops_agent.create_incident(
                    supabase_client,
                    incident_type="sms_dead_letter",
                    severity="P1",
                    summary=f"SMS-jobb {job_id} hamnade i dead letter efter {new_attempts} försök.",
                    restaurant_uuid=restaurant_uuid,
                    restaurant_id=restaurant_id,
                    order_id=row.get("order_id"),
                    human_required=True,
                    details={"error": str(result.get("error") or "")[:500]},
                )
                summary["dead_letter"] += 1
            except Exception as e:
                print(f"ops_worker: dead-letter update fail: {e}")
        else:
            try:
                next_delta = _next_backoff_seconds(new_attempts)
                next_ts = (datetime.utcnow() + timedelta(seconds=next_delta)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                supabase_client.table("sms_jobs").update(
                    {
                        "status": "pending",
                        "updated_at": _now_iso(),
                        "next_attempt_at": next_ts,
                        "last_error": str(result.get("error") or "")[:300],
                    }
                ).eq("id", job_id).execute()
                summary["failed"] += 1
            except Exception as e:
                print(f"ops_worker: backoff update fail: {e}")
    return summary


def reconcile_tenant_health(
    supabase_client: Any,
    *,
    green_period_seconds: int = ops_agent.INTAKE_RESUME_GREEN_PERIOD_SEC,
) -> Dict[str, Any]:
    """
    Återöppna tenants som pausats pga supabase_insert_failures om de varit gröna länge.
    Säkerhetspauser (manual_pause, auth_failure, ...) återöppnas ALDRIG av agenten.
    """
    summary = {"checked": 0, "resumed": 0}
    if not supabase_client:
        return summary
    try:
        resp = (
            supabase_client.table("tenant_health")
            .select("*")
            .eq("intake_status", "paused")
            .execute()
        )
        rows: List[Dict[str, Any]] = getattr(resp, "data", None) or []
    except Exception as e:
        print(f"ops_worker: tenant_health select fail: {e}")
        return summary

    summary["checked"] = len(rows)
    cutoff = datetime.utcnow() - timedelta(seconds=int(green_period_seconds))
    for row in rows:
        reason = (row.get("intake_paused_reason") or "").strip().lower()
        # Endast denna automatiska orsak tillåter agent-resume.
        if reason != "supabase_insert_failures":
            continue
        # Resumera när tenant_health-raden inte uppdaterats under green_period_seconds
        # (= inga nya Supabase-insertfel registrerats sedan dess).
        updated_at = _from_iso(row.get("updated_at"))
        if updated_at is None or updated_at > cutoff:
            continue
        rest_uuid = row.get("restaurant_uuid")
        rest_id = row.get("restaurant_id")
        # Manuell flagga eftersom agentens eget skydd ej tillåter automatisk resume utan
        # explicit grön period. Vi har redan verifierat det här i workern.
        ok, _ = ops_agent.safe_resume_tenant_intake(
            supabase_client,
            restaurant_uuid=rest_uuid,
            restaurant_id=rest_id,
            actor="human",  # Workern äger green-period-policyn här.
        )
        if ok:
            summary["resumed"] += 1
    return summary


def cleanup_idempotency(
    supabase_client: Any,
    *,
    older_than_hours: int = 24,
) -> Dict[str, Any]:
    summary = {"deleted": 0}
    if not supabase_client:
        return summary
    cutoff = (datetime.utcnow() - timedelta(hours=int(older_than_hours))).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    try:
        resp = (
            supabase_client.table("idempotency_records")
            .delete()
            .in_("status", ["completed", "failed"])
            .lt("created_at", cutoff)
            .execute()
        )
        data = getattr(resp, "data", None) or []
        summary["deleted"] = len(data) if isinstance(data, list) else 0
    except Exception as e:
        print(f"ops_worker: cleanup_idempotency fail: {e}")
    return summary


def auto_resolve_stale_incidents(
    supabase_client: Any,
    *,
    older_than_hours: int = 72,
) -> Dict[str, Any]:
    """
    Auto-stäng gamla P2/P3/INFO-incidenter så listan inte växer i oändlighet
    och operatören bara ser sådant som är aktuellt. P0/P1 stängs ALDRIG
    automatiskt – de kräver människa.
    """
    summary = {"resolved": 0}
    if not supabase_client:
        return summary
    cutoff = (datetime.utcnow() - timedelta(hours=int(older_than_hours))).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    try:
        resp = (
            supabase_client.table("incidents")
            .update({"status": "resolved"})
            .eq("status", "open")
            .in_("severity", ["P2", "P3", "INFO"])
            .lt("created_at", cutoff)
            .execute()
        )
        data = getattr(resp, "data", None) or []
        summary["resolved"] = len(data) if isinstance(data, list) else 0
    except Exception as e:
        print(f"ops_worker: auto_resolve_stale_incidents fail: {e}")
    return summary


def cleanup_call_state(
    supabase_client: Any,
    *,
    older_than_hours: int = 2,
) -> Dict[str, Any]:
    """Rensa gamla call_state-rader (samtal är sekunder–minuter långa; 2h är generöst)."""
    summary = {"deleted": 0}
    if not supabase_client:
        return summary
    cutoff = (datetime.utcnow() - timedelta(hours=int(older_than_hours))).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    try:
        resp = (
            supabase_client.table("call_state")
            .delete()
            .lt("updated_at", cutoff)
            .execute()
        )
        data = getattr(resp, "data", None) or []
        summary["deleted"] = len(data) if isinstance(data, list) else 0
    except Exception as e:
        print(f"ops_worker: cleanup_call_state fail: {e}")
    return summary


def maybe_run_daily_backup(
    supabase_client: Any,
    *,
    encryption_key: Optional[str],
) -> Dict[str, Any]:
    """
    Kör en krypterad backup till Supabase Storage EN gång per UTC-dygn.

    Ersätter beroendet av GitHubs opålitliga cron: eftersom Railway-appen kör
    dygnet runt triggas backupen av första ops-ticken varje nytt dygn. En markör
    i ops_settings (last_backup_date) gör den idempotent över omstarter, så vi
    aldrig backar upp flera gånger samma dag. Soft-fail överallt – en misslyckad
    backup får aldrig störa övrig drift.
    """
    summary: Dict[str, Any] = {"ran": False, "ok": False}
    if not supabase_client:
        summary["error"] = "supabase_not_configured"
        return summary
    if not encryption_key:
        summary["error"] = "backup_encryption_key_missing"
        return summary
    today = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        resp = (
            supabase_client.table("ops_settings")
            .select("value")
            .eq("key", "last_backup_date")
            .limit(1)
            .execute()
        )
        rows = getattr(resp, "data", None) or []
        if rows and (rows[0].get("value") or "") == today:
            return {"ran": False, "ok": True, "reason": "already_completed"}
    except Exception as e:
        print(f"ops_worker: last_backup_date read soft-fail: {e}")

    summary["ran"] = True
    try:
        import backup_core

        result = backup_core.run_backup_to_storage(supabase_client, encryption_key, date_str=today)
        supabase_client.table("ops_settings").upsert(
            {"key": "last_backup_date", "value": today, "updated_at": _now_iso()},
            on_conflict="key",
        ).execute()
        summary.update(result)
        print(f"ops_worker: daglig backup klar {result}")
    except Exception as e:
        print(f"ops_worker: daily backup soft-fail: {e}")
        summary["ok"] = False
        summary["error"] = str(e)
    return summary


def run_tick(
    supabase_client: Any,
    *,
    sms_sender: Optional[Callable[[str, str], Dict[str, Any]]] = None,
    backup_encryption_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Kör en hel ops-tick. Returnerar audit-summary."""
    started = time.time()
    sms = process_sms_jobs(supabase_client, sms_sender=sms_sender)
    health = reconcile_tenant_health(supabase_client)
    cleanup = cleanup_idempotency(supabase_client)
    incidents = auto_resolve_stale_incidents(supabase_client)
    call_state = cleanup_call_state(supabase_client)
    backup = maybe_run_daily_backup(supabase_client, encryption_key=backup_encryption_key)
    duration = round(time.time() - started, 3)
    summary = {
        "duration_sec": duration,
        "sms": sms,
        "health": health,
        "cleanup": cleanup,
        "incidents": incidents,
        "call_state": call_state,
        "backup": backup,
        "ts": _now_iso(),
    }
    print(f"ops_worker: tick done {summary}")
    return summary
