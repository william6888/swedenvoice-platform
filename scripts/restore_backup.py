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
import gzip
import json
import os
import sys
from pathlib import Path

import requests
from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_KEY") or ""
BACKUP_KEY = os.getenv("BACKUP_ENCRYPTION_KEY") or ""

# Konfliktkolumn för upsert per tabell (PostgREST on_conflict).
UPSERT_KEYS = {
    "restaurants": "id",
    "restaurant_members": "id",
    "restaurant_secrets": "id",
    "menus": "restaurant_uuid",
    "orders": "id",
    "order_events": "id",
    "sms_jobs": "id",
    "incidents": "id",
    "ops_actions": "id",
    "ops_settings": "key",
    "tenant_health": "restaurant_uuid",
    "idempotency_records": "id",
    "call_state": "call_id",
}


def decrypt(path: str) -> dict:
    if not BACKUP_KEY:
        print("❌ BACKUP_ENCRYPTION_KEY saknas i .env")
        sys.exit(1)
    blob = Path(path).read_bytes()
    try:
        raw = Fernet(BACKUP_KEY.encode()).decrypt(blob)
    except InvalidToken:
        print("❌ Fel nyckel eller korrupt fil – kunde inte dekryptera")
        sys.exit(1)
    return json.loads(gzip.decompress(raw).decode("utf-8"))


def restore_table(dump: dict, table: str) -> None:
    rows = dump["tables"].get(table)
    if rows is None:
        print(f"❌ Tabellen '{table}' finns inte i backupen")
        sys.exit(1)
    if not rows:
        print(f"ℹ️  '{table}' är tom i backupen – inget att återställa")
        return
    key = UPSERT_KEYS.get(table, "id")
    print(f"Återställer {len(rows)} rader till '{table}' (upsert på {key}) ...")
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    # Batcha i lagom bitar.
    for i in range(0, len(rows), 500):
        batch = rows[i : i + 500]
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={key}",
            headers=headers, json=batch, timeout=60,
        )
        if not r.ok:
            print(f"❌ Batch {i}-{i+len(batch)}: {r.status_code} {r.text[:300]}")
            sys.exit(1)
        print(f"  ✅ {i + len(batch)}/{len(rows)}")
    print(f"🎉 '{table}' återställd.")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("backup_file")
    p.add_argument("--export", metavar="FIL", help="Skriv dekrypterad JSON till fil")
    p.add_argument("--restore-table", metavar="TABELL", help="Upserta en tabell till Supabase")
    args = p.parse_args()

    dump = decrypt(args.backup_file)
    print(f"Backup skapad: {dump.get('created_at')}  (format v{dump.get('format_version')})")
    for table, rows in dump["tables"].items():
        print(f"  {table}: {len(rows)} rader")

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
