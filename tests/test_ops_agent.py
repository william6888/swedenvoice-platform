"""Tester för ops-agentens säkra autonoma åtgärder."""

from tests.fake_supabase import FakeSupabase

import ops_agent


def test_log_action_blocks_unsafe_action():
    db = FakeSupabase()
    ops_agent.log_action(
        db,
        action="DROP_TABLE",
        restaurant_uuid="u",
        restaurant_id="r",
        reason="oops",
    )
    assert len(db.get_orders()) == 0
    assert "ops_actions" not in db.tables  # blockerades innan insert


def test_log_action_writes_when_safe():
    db = FakeSupabase()
    ops_agent.log_action(
        db, action="invalidate_menu_cache",
        restaurant_uuid="u", restaurant_id="r", reason="manual",
    )
    rows = db.tables.get("ops_actions", [])
    assert len(rows) == 1
    assert rows[0]["action"] == "invalidate_menu_cache"


def test_create_incident_persists():
    db = FakeSupabase()
    iid = ops_agent.create_incident(
        db, incident_type="t", severity="P1",
        summary="boom", restaurant_uuid="u", restaurant_id="r",
        human_required=True,
    )
    assert iid
    rows = db.tables.get("incidents", [])
    assert rows[0]["status"] == "open"
    assert rows[0]["severity"] == "P1"


def test_supabase_failures_pause_intake_after_threshold():
    db = FakeSupabase()
    for _ in range(ops_agent.SUPABASE_FAIL_PAUSE_THRESHOLD):
        ops_agent.record_supabase_failure(
            db, restaurant_uuid="u", restaurant_id="r",
            error_message="boom", correlation_id=None, order_id=None,
        )
    health = ops_agent.get_tenant_health(db, "u")
    assert health["intake_status"] == "paused"
    assert health["intake_paused_reason"] == "supabase_insert_failures"
    paused, reason = ops_agent.is_intake_paused(db, "u")
    assert paused
    assert reason == "supabase_insert_failures"


def test_supabase_success_resets_counter():
    db = FakeSupabase()
    ops_agent.record_supabase_failure(
        db, restaurant_uuid="u", restaurant_id="r",
        error_message="boom", correlation_id=None, order_id=None,
    )
    ops_agent.record_supabase_success(db, restaurant_uuid="u", restaurant_id="r", order_id="O1")
    health = ops_agent.get_tenant_health(db, "u")
    assert health["consecutive_supabase_failures"] == 0


def test_safe_resume_only_allows_human_for_pause_without_green_period():
    db = FakeSupabase()
    ops_agent.upsert_tenant_health(
        db, restaurant_uuid="u", restaurant_id="r",
        intake_status="paused", intake_paused_reason="supabase_insert_failures",
    )
    ok, msg = ops_agent.safe_resume_tenant_intake(db, restaurant_uuid="u", restaurant_id="r", actor="ops_worker")
    assert not ok
    assert msg == "no_green_period"
    ok2, msg2 = ops_agent.safe_resume_tenant_intake(db, restaurant_uuid="u", restaurant_id="r", actor="human")
    assert ok2
    assert msg2 == "resumed"


def test_queue_sms_job_uses_missing_phone_status_when_empty():
    db = FakeSupabase()
    ops_agent.queue_sms_job(
        db, restaurant_uuid="u", restaurant_id="r",
        order_id="O1", db_order_id=None, to_number="", body="hi",
    )
    rows = db.tables.get("sms_jobs", [])
    assert rows
    assert rows[0]["status"] == "missing_phone"


def test_p1_incident_triggers_alert_sender():
    """P0/P1-incidenter måste nå operatören via registrerad larmkanal."""
    db = FakeSupabase()
    delivered = []
    ops_agent.set_alert_sender(lambda sev, title, body: delivered.append((sev, title, body)))
    try:
        ops_agent.create_incident(
            db, incident_type="supabase_insert_failed", severity="P0",
            summary="boom", restaurant_uuid="u", restaurant_id="r", human_required=True,
        )
        ops_agent.create_incident(
            db, incident_type="info_only", severity="P2",
            summary="minor", restaurant_uuid="u", restaurant_id="r",
        )
    finally:
        ops_agent.set_alert_sender(None)
    # Endast P0 ska ha larmats (P2 är för lågt).
    assert len(delivered) == 1
    assert delivered[0][0] == "P0"


def test_alert_sender_soft_fails_and_never_raises():
    """Om larmkanalen kastar fel får det ALDRIG bubbla upp i hot path."""
    db = FakeSupabase()

    def boom(sev, title, body):
        raise RuntimeError("channel down")

    ops_agent.set_alert_sender(boom)
    try:
        # Ska inte kasta trots att sender kraschar.
        iid = ops_agent.create_incident(
            db, incident_type="t", severity="P1", summary="x",
            restaurant_uuid="u", restaurant_id="r",
        )
        assert iid
    finally:
        ops_agent.set_alert_sender(None)
