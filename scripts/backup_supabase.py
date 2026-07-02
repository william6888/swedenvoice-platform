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
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

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
    total = sum(len(v) for v in dump["tables"].values())
    for table, rows in dump["tables"].items():
        print(f"  ✅ {table}: {len(rows)} rader")

    blob = backup_core.build_encrypted_blob(dump, BACKUP_KEY)
    out = args.out or f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.enc"
    Path(out).write_bytes(blob)
    print(f"\n🔒 Krypterad backup: {out} ({len(blob)} bytes, {total} rader, {len(dump['tables'])} tabeller)")

    if args.to_storage:
        try:
            res = backup_core.run_backup_to_storage(client, BACKUP_KEY)
            print(f"☁️  Uppladdad till Supabase Storage: {res['path']}")
        except Exception as e:
            print(f"⚠️  Storage-uppladdning misslyckades: {e}")


if __name__ == "__main__":
    main()
