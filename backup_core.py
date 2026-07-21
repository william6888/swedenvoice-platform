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
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping

# Alla tabeller som utgör systemets tillstånd och deras riktiga primärnycklar.
# Samma karta används vid export och restore för att de två delarna inte ska
# kunna glida isär.
TABLE_PRIMARY_KEYS: Dict[str, str] = {
    "restaurants": "id",
    "restaurant_members": "id",
    "restaurant_secrets": "restaurant_uuid",
    "menus": "restaurant_uuid",
    "orders": "id",
    "order_events": "id",
    "sms_jobs": "id",
    "incidents": "id",
    "ops_actions": "id",
    "ops_settings": "key",
    "tenant_health": "restaurant_uuid",
    "idempotency_records": "key",
    "call_state": "call_id",
}
TABLES = list(TABLE_PRIMARY_KEYS)

PAGE_SIZE = 1000
BACKUP_BUCKET = "backups"
FORMAT_VERSION = 2


class BackupError(RuntimeError):
    """Backupen är ofullständig eller kunde inte verifieras."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def export_all_tables(supabase_client: Any) -> Dict[str, Any]:
    """
    Hämta alla rader från alla tabeller via stabil keyset-paginering.

    Exporten är fail-closed: om en enda tabell inte kan läsas avbryts hela
    backupen. En tom lista efter ett API-fel får aldrig se ut som en lyckad
    backup.
    """
    if not supabase_client:
        raise BackupError("Supabase-klient saknas")

    dump: Dict[str, Any] = {
        "created_at": _utc_now_iso(),
        "format_version": FORMAT_VERSION,
        "tables": {},
        "manifest": {
            "required_tables": list(TABLES),
            "primary_keys": dict(TABLE_PRIMARY_KEYS),
            "row_counts": {},
            "total_rows": 0,
        },
    }
    for table in TABLES:
        rows: List[Dict[str, Any]] = []
        primary_key = TABLE_PRIMARY_KEYS[table]
        last_key: Any = None
        while True:
            try:
                query = (
                    supabase_client.table(table)
                    .select("*")
                    .order(primary_key, desc=False)
                    .limit(PAGE_SIZE)
                )
                if last_key is not None:
                    query = query.gt(primary_key, last_key)
                resp = query.execute()
                batch = getattr(resp, "data", None) or []
            except Exception as e:
                raise BackupError(f"Kunde inte exportera tabellen '{table}': {e}") from e

            if not isinstance(batch, list) or any(not isinstance(row, dict) for row in batch):
                raise BackupError(f"Ogiltigt API-svar vid export av tabellen '{table}'")
            rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                break

            next_key = batch[-1].get(primary_key)
            if next_key is None or next_key == last_key:
                raise BackupError(
                    f"Pagineringen för '{table}' kunde inte avancera på primärnyckeln '{primary_key}'"
                )
            last_key = next_key

        keys = [row.get(primary_key) for row in rows]
        if any(key is None for key in keys):
            raise BackupError(f"Tabellen '{table}' innehåller rad utan primärnyckeln '{primary_key}'")
        if len(keys) != len(set(keys)):
            raise BackupError(f"Tabellen '{table}' exporterades med dubbla primärnycklar")

        dump["tables"][table] = rows
        dump["manifest"]["row_counts"][table] = len(rows)

    dump["manifest"]["total_rows"] = sum(dump["manifest"]["row_counts"].values())
    validate_dump(dump)
    return dump


def validate_dump(dump: Mapping[str, Any]) -> Dict[str, int]:
    """
    Validera struktur och manifest. Format v1 stöds för gamla backuper.

    Returnerar verifierade radantal per tabell.
    """
    if not isinstance(dump, Mapping):
        raise BackupError("Backupens rot är inte ett JSON-objekt")
    version = dump.get("format_version")
    if version not in (1, FORMAT_VERSION):
        raise BackupError(f"Backupformat {version!r} stöds inte")
    if not dump.get("created_at"):
        raise BackupError("Backupen saknar created_at")

    tables = dump.get("tables")
    if not isinstance(tables, Mapping):
        raise BackupError("Backupen saknar ett giltigt tables-objekt")
    missing = [table for table in TABLES if table not in tables]
    if missing:
        raise BackupError(f"Backupen saknar obligatoriska tabeller: {', '.join(missing)}")

    row_counts: Dict[str, int] = {}
    for table in TABLES:
        rows = tables[table]
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise BackupError(f"Tabellen '{table}' har ogiltigt radformat")
        row_counts[table] = len(rows)

    if version == FORMAT_VERSION:
        manifest = dump.get("manifest")
        if not isinstance(manifest, Mapping):
            raise BackupError("Format v2 saknar manifest")
        if manifest.get("required_tables") != TABLES:
            raise BackupError("Manifestets tabellista matchar inte det förväntade schemat")
        if manifest.get("primary_keys") != TABLE_PRIMARY_KEYS:
            raise BackupError("Manifestets primärnycklar matchar inte det förväntade schemat")
        if manifest.get("row_counts") != row_counts:
            raise BackupError("Manifestets radantal matchar inte backupens innehåll")
        if manifest.get("total_rows") != sum(row_counts.values()):
            raise BackupError("Manifestets totala radantal är fel")

    return row_counts


def build_encrypted_blob(dump: Dict[str, Any], encryption_key: str) -> bytes:
    """Serialisera → gzip → Fernet-kryptera. Returnerar krypterade bytes."""
    from cryptography.fernet import Fernet

    validate_dump(dump)
    raw = json.dumps(dump, ensure_ascii=False, default=str).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(raw)
    return Fernet(encryption_key.encode()).encrypt(buf.getvalue())


def decrypt_blob(blob: bytes, encryption_key: str) -> Dict[str, Any]:
    """Motsatsen till build_encrypted_blob: Fernet-dekryptera → gunzip → JSON."""
    from cryptography.fernet import Fernet

    raw = Fernet(encryption_key.encode()).decrypt(blob)
    try:
        dump = json.loads(gzip.decompress(raw).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise BackupError(f"Krypterat innehåll har ogiltigt gzip/JSON-format: {e}") from e
    validate_dump(dump)
    return dump


def upload_verified_blob(
    supabase_client: Any,
    blob: bytes,
    encryption_key: str,
    *,
    path: str,
    bucket: str = BACKUP_BUCKET,
) -> None:
    """Ladda upp och läs genast tillbaka objektet; avbryt om bytes/format skiljer."""
    storage = supabase_client.storage.from_(bucket)
    storage.upload(
        path, blob, {"content-type": "application/octet-stream", "upsert": "true"}
    )
    downloaded = storage.download(path)
    if not isinstance(downloaded, (bytes, bytearray)) or bytes(downloaded) != blob:
        raise BackupError(f"Verifiering av uppladdad backup misslyckades: {bucket}/{path}")
    decrypt_blob(bytes(downloaded), encryption_key)


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
    date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dump = export_all_tables(supabase_client)
    row_counts = validate_dump(dump)
    rows = sum(row_counts.values())
    blob = build_encrypted_blob(dump, encryption_key)
    path = f"backup_{date_str}.enc"
    upload_verified_blob(
        supabase_client, blob, encryption_key, path=path, bucket=bucket
    )
    return {
        "ok": True,
        "verified": True,
        "path": path,
        "bytes": len(blob),
        "rows": rows,
        "row_counts": row_counts,
    }
