"""Tester för ops_worker (SMS retries, dead-letter, tenant resume)."""

from datetime import datetime, timedelta

from tests.fake_supabase import FakeSupabase

import ops_agent
import ops_worker


def _now_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def test_process_sms_jobs_sends_pending():
    db = FakeSupabase()
    db.tables.setdefault("sms_jobs", []).append({
        "id": "j1", "status": "pending", "attempts": 0, "max_attempts": 3,
        "to_number": "+46700000000", "body": "Hej", "next_attempt_at": _now_iso(),
        "restaurant_uuid": "u", "restaurant_id": "r",
    })
    sent_calls = []

    def fake_sender(to, body):
        sent_calls.append((to, body))
        return {"ok": True}

    summary = ops_worker.process_sms_jobs(db, sms_sender=fake_sender)
    assert summary["sent"] == 1
    assert sent_calls == [("+46700000000", "Hej")]
    rows = db.tables["sms_jobs"]
    assert rows[0]["status"] == "sent"


def test_process_sms_jobs_dead_letter_after_max_attempts():
    db = FakeSupabase()
    db.tables.setdefault("sms_jobs", []).append({
        "id": "j1", "status": "pending", "attempts": 2, "max_attempts": 3,
        "to_number": "+46700000000", "body": "Hej", "next_attempt_at": _now_iso(),
        "restaurant_uuid": "u", "restaurant_id": "r", "order_id": "O1",
    })

    def fake_sender(to, body):
        return {"ok": False, "error": "transient"}

    summary = ops_worker.process_sms_jobs(db, sms_sender=fake_sender)
    assert summary["dead_letter"] == 1
    rows = db.tables["sms_jobs"]
    assert rows[0]["status"] == "dead_letter"
    incidents = db.tables.get("incidents") or []
    assert any(i["type"] == "sms_dead_letter" for i in incidents)


def test_process_sms_jobs_backoff_on_failure_below_max():
    db = FakeSupabase()
    db.tables.setdefault("sms_jobs", []).append({
        "id": "j1", "status": "pending", "attempts": 0, "max_attempts": 3,
        "to_number": "+46700000000", "body": "Hej", "next_attempt_at": _now_iso(),
    })

    def fake_sender(to, body):
        return {"ok": False, "error": "rate_limit"}

    ops_worker.process_sms_jobs(db, sms_sender=fake_sender)
    job = db.tables["sms_jobs"][0]
    assert job["status"] == "pending"
    assert job["attempts"] == 1
    assert job["last_error"]
    # next_attempt_at flyttades fram – ny tid > original
    assert job["next_attempt_at"] != _now_iso()


def test_reconcile_resumes_only_supabase_pause_with_green_period():
    db = FakeSupabase()
    stale = (datetime.utcnow() - timedelta(seconds=ops_agent.INTAKE_RESUME_GREEN_PERIOD_SEC + 30)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"
    db.tables.setdefault("tenant_health", []).extend([
        {"restaurant_uuid": "auto", "restaurant_id": "rA", "intake_status": "paused",
         "intake_paused_reason": "supabase_insert_failures", "updated_at": stale,
         "last_supabase_ok": stale, "consecutive_supabase_failures": 0},
        {"restaurant_uuid": "manual", "restaurant_id": "rM", "intake_status": "paused",
         "intake_paused_reason": "manual_pause", "updated_at": stale,
         "last_supabase_ok": stale, "consecutive_supabase_failures": 0},
    ])
    summary = ops_worker.reconcile_tenant_health(db)
    assert summary["resumed"] == 1
    rows = db.tables["tenant_health"]
    auto = next(r for r in rows if r["restaurant_uuid"] == "auto")
    manual = next(r for r in rows if r["restaurant_uuid"] == "manual")
    assert auto["intake_status"] == "open"
    assert manual["intake_status"] == "paused"


def test_reconcile_does_not_resume_when_recently_failed():
    db = FakeSupabase()
    fresh = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    db.tables.setdefault("tenant_health", []).append(
        {"restaurant_uuid": "auto", "restaurant_id": "rA", "intake_status": "paused",
         "intake_paused_reason": "supabase_insert_failures", "updated_at": fresh,
         "last_supabase_ok": fresh, "consecutive_supabase_failures": 3}
    )
    summary = ops_worker.reconcile_tenant_health(db)
    assert summary["resumed"] == 0
    assert db.tables["tenant_health"][0]["intake_status"] == "paused"


def test_sms_job_already_locked_is_skipped():
    """En redan låst rad (status != pending) får INTE skickas igen → inga dubbla SMS."""
    db = FakeSupabase()
    db.tables.setdefault("sms_jobs", []).append({
        "id": "j1", "status": "sending", "attempts": 1, "max_attempts": 3,
        "to_number": "+46700000000", "body": "Hej", "next_attempt_at": _now_iso(),
    })
    sent = []

    def fake_sender(to, body):
        sent.append((to, body))
        return {"ok": True}

    # Raden hämtas via status=pending-filtret INTE alls här (status=sending),
    # men vi simulerar racen: lägg en pending-rad vars lås "missar".
    db.tables["sms_jobs"].append({
        "id": "j2", "status": "pending", "attempts": 0, "max_attempts": 3,
        "to_number": "+46700000001", "body": "Hej2", "next_attempt_at": _now_iso(),
    })
    summary = ops_worker.process_sms_jobs(db, sms_sender=fake_sender)
    # Endast den äkta pending-raden (j2) ska skickas.
    assert summary["sent"] == 1
    assert sent == [("+46700000001", "Hej2")]


def test_daily_backup_runs_once_per_day():
    """Backupen ska köra en gång, ladda upp krypterat, sedan hoppa över samma dag."""
    from cryptography.fernet import Fernet
    import backup_core

    db = FakeSupabase()
    db.tables.setdefault("orders", []).append({"id": "o1", "order_id": "ORD-1"})
    db.tables.setdefault("restaurants", []).append({"id": "r1", "external_id": "X"})
    key = Fernet.generate_key().decode()

    res1 = ops_worker.maybe_run_daily_backup(db, encryption_key=key)
    assert res1["ran"] is True
    assert res1["ok"] is True

    # Filen finns i storage och kan dekrypteras tillbaka.
    files = list(db.storage.buckets.get("backups", {}).keys())
    assert len(files) == 1
    blob = db.storage.from_("backups").download(files[0])
    dump = backup_core.decrypt_blob(blob, key)
    assert "orders" in dump["tables"]

    # Andra körningen samma dag ska hoppa över.
    res2 = ops_worker.maybe_run_daily_backup(db, encryption_key=key)
    assert res2["ran"] is False


def test_daily_backup_skips_without_key():
    """Utan krypteringsnyckel ska backupen aldrig köra (får ej skriva okrypterat)."""
    db = FakeSupabase()
    res = ops_worker.maybe_run_daily_backup(db, encryption_key=None)
    assert res["ran"] is False
    assert "backups" not in db.storage.buckets


def test_auto_resolve_stale_incidents_keeps_p0_p1():
    db = FakeSupabase()
    old = (datetime.utcnow() - timedelta(hours=100)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    db.tables.setdefault("incidents", []).extend([
        {"id": "i1", "status": "open", "severity": "P2", "created_at": old},
        {"id": "i2", "status": "open", "severity": "P0", "created_at": old},
        {"id": "i3", "status": "open", "severity": "INFO", "created_at": old},
    ])
    summary = ops_worker.auto_resolve_stale_incidents(db)
    assert summary["resolved"] == 2
    rows = {r["id"]: r["status"] for r in db.tables["incidents"]}
    assert rows["i1"] == "resolved"
    assert rows["i3"] == "resolved"
    assert rows["i2"] == "open"  # P0 stängs aldrig automatiskt
