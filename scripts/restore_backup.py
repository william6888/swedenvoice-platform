#!/usr/bin/env python3
"""
Läs/återställ en krypterad Supabase-backup skapad av scripts/backup_supabase.py.

Säkert som standard: utan flaggor visas bara innehållet (inget skrivs).
Återställning sker per tabell och kräver en explicit flagga.

Användning:
  # 1. Inspektera (skriver INGET till databasen)
  python3 scripts/restore_backup.py backup_20260702.enc

  # 2. Exportera dekrypterad JSON för manuell hantering
  python3 scripts/restore_backup.py backup_20260702.enc --export dump.json

  # 3. Återställ EN tabell (upsert på primärnyckel via PostgREST)
  python3 scripts/restore_backup.py backup_20260702.enc --restore-table orders

Kräver BACKUP_ENCRYPTION_KEY + SUPABASE_URL/SUPABASE_KEY i .env (samma som backupen).
"""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from cryptography.fernet import InvalidToken

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from env_loader import load_env_file

load_env_file(ROOT / ".env")

import backup_core

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_KEY") or ""
BACKUP_KEY = os.getenv("BACKUP_ENCRYPTION_KEY") or ""

# En gemensam källa för exportens och restore-flödets riktiga primärnycklar.
UPSERT_KEYS = backup_core.TABLE_PRIMARY_KEYS


def decrypt_bytes(blob: bytes) -> dict:
    if not BACKUP_KEY:
        print("❌ BACKUP_ENCRYPTION_KEY saknas i .env")
        sys.exit(1)
    try:
        return backup_core.decrypt_blob(blob, BACKUP_KEY)
    except InvalidToken:
        print("❌ Fel nyckel eller korrupt fil – kunde inte dekryptera")
        sys.exit(1)
    except (backup_core.BackupError, ValueError, json.JSONDecodeError) as e:
        print(f"❌ Backupen är ofullständig eller ogiltig: {e}")
        sys.exit(1)


def decrypt(path: str) -> dict:
    return decrypt_bytes(Path(path).read_bytes())


def download_from_storage(name: str) -> bytes:
    """Ladda ner en krypterad backup från Supabase Storage-bucket 'backups'."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ SUPABASE_URL/SUPABASE_KEY saknas")
        sys.exit(1)
    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return client.storage.from_("backups").download(name)


def restore_table(dump: dict, table: str) -> None:
    if table not in UPSERT_KEYS:
        print(f"❌ Tabellen '{table}' är inte tillåten för automatisk återställning")
        sys.exit(1)
    rows = dump["tables"].get(table)
    if rows is None:
        print(f"❌ Tabellen '{table}' finns inte i backupen")
        sys.exit(1)
    if not rows:
        print(f"ℹ️  '{table}' är tom i backupen – inget att återställa")
        return
    key = UPSERT_KEYS[table]
    if any(row.get(key) is None for row in rows):
        print(f"❌ '{table}' innehåller rad utan primärnyckeln '{key}'")
        sys.exit(1)
    print(f"Återställer {len(rows)} rader till '{table}' (upsert på {key}) ...")
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    # Batcha i lagom bitar.
    for i in range(0, len(rows), 500):
        batch = rows[i : i + 500]
        r = httpx.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            params={"on_conflict": key},
            headers=headers,
            json=batch,
            timeout=60,
        )
        if not r.is_success:
            print(f"❌ Batch {i}-{i+len(batch)}: {r.status_code} {r.text[:300]}")
            sys.exit(1)
        try:
            restored = r.json()
        except ValueError:
            restored = None
        if not isinstance(restored, list) or len(restored) != len(batch):
            print(
                f"❌ Batch {i}-{i+len(batch)} gav inte verifierat radantal "
                f"(förväntat {len(batch)})"
            )
            sys.exit(1)
        print(f"  ✅ {i + len(batch)}/{len(rows)}")
    print(f"🎉 '{table}' återställd.")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("backup_file", nargs="?", help="Lokal .enc-fil (utelämna om --from-storage)")
    p.add_argument("--from-storage", metavar="NAMN", help="Ladda ner från Supabase Storage, t.ex. backup_2026-07-02.enc")
    p.add_argument("--export", metavar="FIL", help="Skriv dekrypterad JSON till fil")
    p.add_argument(
        "--restore-table",
        metavar="TABELL",
        choices=backup_core.TABLES,
        help="Upserta en tillåten tabell till Supabase",
    )
    args = p.parse_args()

    if args.from_storage:
        dump = decrypt_bytes(download_from_storage(args.from_storage))
    elif args.backup_file:
        dump = decrypt(args.backup_file)
    else:
        print("❌ Ange en lokal fil eller --from-storage NAMN")
        sys.exit(1)
    row_counts = backup_core.validate_dump(dump)
    print(f"Backup skapad: {dump.get('created_at')}  (format v{dump.get('format_version')})")
    for table in backup_core.TABLES:
        print(f"  {table}: {row_counts[table]} rader")
    print(f"✅ Backup verifierad: {sum(row_counts.values())} rader i {len(row_counts)} tabeller")

    if args.export:
        Path(args.export).write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n📄 Dekrypterad JSON: {args.export} (radera filen när du är klar – innehåller PII)")

    if args.restore_table:
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("❌ SUPABASE_URL/SUPABASE_KEY saknas")
            sys.exit(1)
        confirm = input(f"Skriv '{args.restore_table}' för att bekräfta återställning: ").strip()
        if confirm != args.restore_table:
            print("Avbrutet.")
            sys.exit(0)
        restore_table(dump, args.restore_table)


if __name__ == "__main__":
    main()
