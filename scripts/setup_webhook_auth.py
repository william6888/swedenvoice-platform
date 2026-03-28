#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gör webhook-auth så enkelt som möjligt:
- Uppdaterar .env med WEBHOOK_SHARED_SECRET
- Skriver ALL instruktion + hemlighet till .webhook_auth_instructions.txt (gitignored)
  så inget behöver klistras i AI-chat.

Kör från projektroten:
  python3 scripts/setup_webhook_auth.py
  python3 scripts/setup_webhook_auth.py --rotate    # ny hemlighet (uppdatera Railway+Vapi)
  python3 scripts/setup_webhook_auth.py --print-secret   # skriv även ut hemlighet i terminal (undvik i Cursor-chat)
"""
from __future__ import print_function

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
INSTRUCTIONS_FILE = ROOT / ".webhook_auth_instructions.txt"
KEY = "WEBHOOK_SHARED_SECRET"


def _extract_existing_secret(text):
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#") or not s:
            continue
        if s.startswith(KEY + "="):
            return s.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _replace_or_append_secret(raw, new_secret):
    lines = raw.splitlines(keepends=True)
    out = []
    replaced = False
    for line in lines:
        if line.strip().startswith(KEY + "="):
            out.append("%s=%s\n" % (KEY, new_secret))
            replaced = True
        else:
            out.append(line)
    if not replaced:
        if out and not out[-1].endswith("\n"):
            out.append("\n")
        out.append("\n# Webhook-auth: samma värde i Railway + Vapi (header nedan)\n")
        out.append("%s=%s\n" % (KEY, new_secret))
    return "".join(out)


def _instructions_text(secret):
    return """================================================================
STEG 1 — RAILWAY (öppna i webbläsaren)
================================================================
  Project → Variables → New Variable
  Name:   WEBHOOK_SHARED_SECRET
  Value:  (kopiera raden under, utan citattecken)

%s

  Spara → Redeploy / Restart så servern läser variabeln.

================================================================
STEG 2 — VAPI
================================================================
  Där Server URL mot Railway finns (Assistant / Phone / Tool):
  HTTP Headers → Add:
    Name:  X-Webhook-Secret
    Value: (samma som ovan, tecken för tecken)

================================================================
OBS
================================================================
- Denna fil committas INTE (ligger i .gitignore).
- Lägg inte värdet i AI-chat eller skärmdumpar.
- Om du misstänker läckage: kör igen med --rotate och uppdatera Railway+Vapi.
""" % secret


def main():
    rotate = "--rotate" in sys.argv
    print_secret = "--print-secret" in sys.argv
    secret = None

    if ENV_FILE.exists():
        raw = ENV_FILE.read_text(encoding="utf-8")
        existing = _extract_existing_secret(raw)
        if existing and not rotate:
            secret = existing
            print("OK: WEBHOOK_SHARED_SECRET finns redan i .env (andras inte). Uppdaterar bara instruktionsfilen.\n")
        else:
            secret = secrets.token_urlsafe(32)
            ENV_FILE.write_text(_replace_or_append_secret(raw, secret), encoding="utf-8")
            if rotate:
                print("OK: Ny WEBHOOK_SHARED_SECRET i .env — uppdatera Railway OCH Vapi med nya värdet!\n")
            else:
                print("OK: WEBHOOK_SHARED_SECRET sparad i .env\n")
    else:
        secret = secrets.token_urlsafe(32)
        print("VARNING: Ingen .env hittades: %s" % ENV_FILE)
        print("Kopiera .env.template till .env och kör skriptet igen.\n")
        print("Tillfälligt värde (lägg manuellt i .env):\n%s=%s\n" % (KEY, secret))

    if secret:
        INSTRUCTIONS_FILE.write_text(_instructions_text(secret), encoding="utf-8")
        print("=" * 60)
        print("ÖPPNA DENNA FIL PÅ DIN DATOR (där finns hemligheten):")
        print("  %s" % INSTRUCTIONS_FILE)
        print("(Filen committas inte till Git.)")
        print("=" * 60)
        if print_secret:
            print()
            print(_instructions_text(secret))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
