"""
Backup-kärna: exportera + kryptera Supabase-tabeller.

Delas av:
  * scripts/backup_supabase.py (manuell/CLI-backup till fil)
  * ops_worker.maybe_run_daily_backup (autonom daglig backup till Supabase Storage,
    körs av Railway-appen dygnet runt – oberoende av GitHubs opålitliga cron och
    av din lokala dator)

Krypteringen (Fernet: AES-128-CBC + HMAC) sker INNAN datan lämnar processen, så
backupen är oläsbar utan BACKUP_ENCRYPTION_KEY – även om lagringsplatsen läcker.
"""

from __future__ import annotations

import gzip
import io
import json
from datetime import datetime
from typing import Any, Dict, List

# Alla tabeller som utgör systemets tillstånd.
TABLES = [
    "restaurants",
    "restaurant_members",
    "restaurant_secrets",
    "menus",
    "orders",
    "order_events",
    "sms_jobs",
    "incidents",
    "ops_actions",
    "ops_settings",
    "tenant_health",
    "idempotency_records",
    "call_state",
]

PAGE_SIZE = 1000
BACKUP_BUCKET = "backups"


def export_all_tables(supabase_client: Any) -> Dict[str, Any]:
    """Hämta alla rader från alla tabeller (paginerat) via supabase-klienten."""
    dump: Dict[str, Any] = {
        "created_at": datetime.utcnow().isoformat() + "Z",
        "format_version": 1,
        "tables": {},
    }
    for table in TABLES:
        rows: List[Dict[str, Any]] = []
        offset = 0
        while True:
            try:
                resp = (
                    supabase_client.table(table)
                    .select("*")
                    .range(offset, offset + PAGE_SIZE - 1)
                    .execute()
                )
                batch = getattr(resp, "data", None) or []
            except Exception as e:
                # Saknad tabell eller fel: ta med tom lista men logga inte hårt.
                print(f"backup_core: {table} export soft-fail: {e}")
                batch = []
            rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        dump["tables"][table] = rows
    return dump


def build_encrypted_blob(dump: Dict[str, Any], encryption_key: str) -> bytes:
    """Serialisera → gzip → Fernet-kryptera. Returnerar krypterade bytes."""
    from cryptography.fernet import Fernet

    raw = json.dumps(dump, ensure_ascii=False, default=str).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(raw)
    return Fernet(encryption_key.encode()).encrypt(buf.getvalue())


def decrypt_blob(blob: bytes, encryption_key: str) -> Dict[str, Any]:
    """Motsatsen till build_encrypted_blob: Fernet-dekryptera → gunzip → JSON."""
    from cryptography.fernet import Fernet

    raw = Fernet(encryption_key.encode()).decrypt(blob)
    return json.loads(gzip.decompress(raw).decode("utf-8"))


def run_backup_to_storage(
    supabase_client: Any,
    encryption_key: str,
    *,
    bucket: str = BACKUP_BUCKET,
    date_str: str | None = None,
) -> Dict[str, Any]:
    """
    Exportera, kryptera och ladda upp till Supabase Storage.
    Filnamn: backup_YYYY-MM-DD.enc (upsert → en fil per dag, idempotent).
    Returnerar {"ok": bool, "path": str, "bytes": int, "rows": int}.
    """
    date_str = date_str or datetime.utcnow().strftime("%Y-%m-%d")
    dump = export_all_tables(supabase_client)
    rows = sum(len(v) for v in dump["tables"].values())
    blob = build_encrypted_blob(dump, encryption_key)
    path = f"backup_{date_str}.enc"
    supabase_client.storage.from_(bucket).upload(
        path, blob, {"content-type": "application/octet-stream", "upsert": "true"}
    )
    return {"ok": True, "path": path, "bytes": len(blob), "rows": rows}
