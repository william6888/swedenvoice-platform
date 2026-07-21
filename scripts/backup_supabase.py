#!/usr/bin/env python3
"""
Manuell krypterad backup av alla kritiska Supabase-tabeller (CLI).

Detta är komplementet till den AUTONOMA dagliga backupen som Railway-appen kör
(ops_worker.maybe_run_daily_backup → Supabase Storage). Använd detta skript för
en backup på begäran, t.ex. före en riskabel migration.

Skriver en lokal krypterad fil (går ej att läsa utan BACKUP_ENCRYPTION_KEY).

Användning:
  python3 scripts/backup_supabase.py                 # backup_YYYYMMDD_HHMMSS.enc
  python3 scripts/backup_supabase.py --out fil.enc
  python3 scripts/backup_supabase.py --to-storage    # ladda även upp till Supabase Storage

Återställning: scripts/restore_backup.py
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from env_loader import load_env_file

load_env_file(ROOT / ".env")

import backup_core

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_KEY") or ""
BACKUP_KEY = os.getenv("BACKUP_ENCRYPTION_KEY") or ""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=None, help="Utfil (.enc). Default: backup_<tidsstämpel>.enc")
    p.add_argument("--to-storage", action="store_true", help="Ladda även upp till Supabase Storage-bucket 'backups'")
    args = p.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ SUPABASE_URL/SUPABASE_KEY saknas (env eller .env)")
        sys.exit(1)
    if not BACKUP_KEY:
        print("❌ BACKUP_ENCRYPTION_KEY saknas – backup får ALDRIG skrivas okrypterad")
        sys.exit(1)

    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    dump = backup_core.export_all_tables(client)
    row_counts = backup_core.validate_dump(dump)
    total = sum(row_counts.values())
    for table in backup_core.TABLES:
        print(f"  ✅ {table}: {row_counts[table]} rader")

    blob = backup_core.build_encrypted_blob(dump, BACKUP_KEY)
    # Självtesta hela kryptering/dekryptering innan filen publiceras.
    backup_core.decrypt_blob(blob, BACKUP_KEY)

    out = args.out or f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.enc"
    out_path = Path(out)
    temp_path = out_path.with_name(f".{out_path.name}.tmp")
    try:
        temp_path.write_bytes(blob)
        temp_path.replace(out_path)
    finally:
        temp_path.unlink(missing_ok=True)
    print(
        f"\n🔒 Krypterad och verifierad backup: {out_path} "
        f"({len(blob)} bytes, {total} rader, {len(row_counts)} tabeller)"
    )

    if args.to_storage:
        storage_path = f"backup_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.enc"
        backup_core.upload_verified_blob(
            client, blob, BACKUP_KEY, path=storage_path
        )
        print(f"☁️  Uppladdad och återläst från Supabase Storage: {storage_path}")


if __name__ == "__main__":
    main()
