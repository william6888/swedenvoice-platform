"""Backup/restore-integritet: fail-closed export, paginering och rätt nycklar."""

import copy

import pytest
from cryptography.fernet import Fernet

import backup_core
from scripts import restore_backup
from tests.fake_supabase import FakeSupabase


def _empty_v1_dump():
    return {
        "created_at": "2026-07-01T00:00:00Z",
        "format_version": 1,
        "tables": {table: [] for table in backup_core.TABLES},
    }


def test_v2_roundtrip_has_verified_manifest():
    db = FakeSupabase()
    db.tables["orders"] = [{"id": "o1", "order_id": "ORD-1"}]
    dump = backup_core.export_all_tables(db)
    key = Fernet.generate_key().decode()

    restored = backup_core.decrypt_blob(
        backup_core.build_encrypted_blob(dump, key), key
    )

    assert restored["format_version"] == 2
    assert restored["manifest"]["row_counts"]["orders"] == 1
    assert restored["manifest"]["total_rows"] == 1


def test_export_fails_closed_if_one_table_cannot_be_read():
    db = FakeSupabase()
    db.simulate_missing_table["order_events"] = True

    with pytest.raises(backup_core.BackupError, match="order_events"):
        backup_core.export_all_tables(db)


def test_keyset_pagination_exports_each_row_exactly_once():
    db = FakeSupabase()
    db.tables["orders"] = [
        {"id": f"o{i:04d}", "order_id": f"ORD-{i}"}
        for i in range(backup_core.PAGE_SIZE + 205)
    ]

    dump = backup_core.export_all_tables(db)
    ids = [row["id"] for row in dump["tables"]["orders"]]

    assert len(ids) == backup_core.PAGE_SIZE + 205
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)


def test_manifest_tampering_is_rejected():
    db = FakeSupabase()
    dump = backup_core.export_all_tables(db)
    tampered = copy.deepcopy(dump)
    tampered["manifest"]["total_rows"] = 99

    with pytest.raises(backup_core.BackupError, match="totala radantal"):
        backup_core.validate_dump(tampered)


def test_storage_upload_is_read_back_and_verified(monkeypatch):
    db = FakeSupabase()
    dump = backup_core.export_all_tables(db)
    key = Fernet.generate_key().decode()
    blob = backup_core.build_encrypted_blob(dump, key)
    bucket_class = type(db.storage.from_("backups"))

    monkeypatch.setattr(bucket_class, "download", lambda self, path: b"corrupt")

    with pytest.raises(backup_core.BackupError, match="Verifiering"):
        backup_core.upload_verified_blob(
            db, blob, key, path="backup_2026-07-21.enc"
        )


def test_old_v1_backup_remains_readable():
    key = Fernet.generate_key().decode()
    dump = _empty_v1_dump()

    restored = backup_core.decrypt_blob(
        backup_core.build_encrypted_blob(dump, key), key
    )

    assert restored["format_version"] == 1
    assert backup_core.validate_dump(restored) == {
        table: 0 for table in backup_core.TABLES
    }


def test_restore_uses_real_primary_keys(monkeypatch):
    calls = []

    class Response:
        ok = True
        status_code = 201
        text = ""

        @staticmethod
        def json():
            return [{"restaurant_uuid": "r1", "encrypted_config": "cipher"}]

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(restore_backup, "SUPABASE_URL", "https://example.invalid")
    monkeypatch.setattr(restore_backup, "SUPABASE_KEY", "service-key")
    monkeypatch.setattr(restore_backup.requests, "post", fake_post)

    restore_backup.restore_table(
        {
            "tables": {
                "restaurant_secrets": [
                    {"restaurant_uuid": "r1", "encrypted_config": "cipher"}
                ]
            }
        },
        "restaurant_secrets",
    )

    assert calls[0][1]["params"] == {"on_conflict": "restaurant_uuid"}
    assert restore_backup.UPSERT_KEYS["idempotency_records"] == "key"
