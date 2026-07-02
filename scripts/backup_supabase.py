#!/usr/bin/env python3
"""
Krypterad backup av alla kritiska Supabase-tabeller.

Gratis-alternativ till Supabase PITR: exporterar tabellerna via service-role-
nyckeln, packar till gzip och krypterar med Fernet (AES-128-CBC + HMAC) innan
filen lämnar maskinen. Körs nattligen av .github/workflows/backup.yml och
sparas som GitHub Actions-artifact (30 dagars historik).

VIKTIGT: Utan BACKUP_ENCRYPTION_KEY är backupen oläsbar. Nyckeln finns i .env
lokalt och som GitHub secret. Förlora den inte.

Användning:
  python3 scripts/backup_supabase.py                 # skriver backup_YYYYMMDD_HHMMSS.enc
  python3 scripts/backup_supabase.py --out fil.enc   # eget filnamn

Återställning: se scripts/restore_backup.py
"""

import argparse
import gzip
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_KEY") or ""
BACKUP_KEY = os.getenv("BACKUP_ENCRYPTION_KEY") or ""

# Alla tabeller som utgör systemets tillstånd. call_state och idempotency_records
# är flyktiga men billiga att ta med – hellre för mycket än för lite.
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


def fetch_table(table: str) -> list:
    """Hämta alla rader (paginerat) via PostgREST med service-role."""
    rows: list = []
    offset = 0
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Range-Unit": "items",
    }
    while True:
        headers["Range"] = f"{offset}-{offset + PAGE_SIZE - 1}"
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?select=*", headers=headers, timeout=30)
        if r.status_code == 404:
            print(f"  ⚠️  {table}: finns inte (hoppar över)")
            return rows
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=None, help="Utfil (.enc). Default: backup_<tidsstämpel>.enc")
    args = p.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ SUPABASE_URL/SUPABASE_KEY saknas (env eller .env)")
        sys.exit(1)
    if not BACKUP_KEY:
        print("❌ BACKUP_ENCRYPTION_KEY saknas – backup får ALDRIG skrivas okrypterad")
        sys.exit(1)

    dump = {
        "created_at": datetime.utcnow().isoformat() + "Z",
        "supabase_url": SUPABASE_URL,
        "format_version": 1,
        "tables": {},
    }
    total = 0
    for table in TABLES:
        try:
            rows = fetch_table(table)
        except Exception as e:
            print(f"  ❌ {table}: {e}")
            sys.exit(1)
        dump["tables"][table] = rows
        total += len(rows)
        print(f"  ✅ {table}: {len(rows)} rader")

    raw = json.dumps(dump, ensure_ascii=False, default=str).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(raw)
    encrypted = Fernet(BACKUP_KEY.encode()).encrypt(buf.getvalue())

    out = args.out or f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.enc"
    Path(out).write_bytes(encrypted)
    print(f"\n🔒 Krypterad backup skriven: {out} ({len(encrypted)} bytes, {total} rader, {len(TABLES)} tabeller)")


if __name__ == "__main__":
    main()
