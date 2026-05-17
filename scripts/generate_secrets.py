#!/usr/bin/env python3
"""
Generera kryptografiskt starka secrets för Railway och visa exakta CLI-kommandon.

Kör:    python3 scripts/generate_secrets.py
Output: deploy_kit/railway_env.txt + deploy_kit/railway_set_vars.sh

OBS: Lagra inte filerna i git. Kopiera värdena till Railway en gång och radera.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path


def gen(n: int = 48) -> str:
    return secrets.token_urlsafe(n)


def main() -> int:
    out_dir = Path(__file__).resolve().parent.parent / "deploy_kit"
    out_dir.mkdir(exist_ok=True)

    # Behåll befintliga secrets om de redan finns i .env, annars generera nya.
    existing = {}
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip().strip('"').strip("'")

    secrets_set = {
        "ADMIN_SECRET": existing.get("ADMIN_SECRET") or gen(40),
        "WEBHOOK_SHARED_SECRET": existing.get("WEBHOOK_SHARED_SECRET") or gen(48),
        "DRAFT_SIGNING_SECRET": existing.get("DRAFT_SIGNING_SECRET") or gen(48),
        "ENCRYPTION_SECRET": existing.get("ENCRYPTION_SECRET") or gen(48),
    }

    flags = {
        "ORDER_REQUIRE_DB_COMMIT": "true",
        "DASHBOARD_FROM_DB": "true",
        "REQUIRE_DRAFT_TOKEN": "true",
        "OPS_AGENT_ENABLED": "true",
        "OPS_AGENT_INTERVAL_SEC": "90",
        "DEFAULT_DASHBOARD_REST_ID": existing.get("DEFAULT_DASHBOARD_REST_ID", "Gislegrillen_01"),
    }

    env_text_lines = []
    env_text_lines.append("# === Genererat av scripts/generate_secrets.py ===")
    env_text_lines.append("# Kopiera VARJE rad in i Railway → Variables.")
    env_text_lines.append("# Ta INTE med rader som redan finns i Railway.")
    env_text_lines.append("# Spara INTE denna fil i git.\n")
    for k, v in secrets_set.items():
        env_text_lines.append(f"{k}={v}")
    env_text_lines.append("")
    env_text_lines.append("# === Order integrity flags (default-värden i koden, men sätt explicit i Railway) ===")
    for k, v in flags.items():
        env_text_lines.append(f"{k}={v}")
    env_text_lines.append("")
    env_text_lines.append("# === Existerande Railway-värden som måste vara satta ===")
    env_text_lines.append("# SUPABASE_URL=...")
    env_text_lines.append("# SUPABASE_KEY=<service_role>")
    env_text_lines.append("# RESTAURANT_UUID=bd525e53-cfb0-4818-a666-90664cd8414f")
    env_text_lines.append("# VAPI_API_KEY=...")
    env_text_lines.append("# VONAGE_API_KEY=...")
    env_text_lines.append("# VONAGE_API_SECRET=...")
    env_text_lines.append("# VONAGE_FROM_NUMBER=...")

    (out_dir / "railway_env.txt").write_text("\n".join(env_text_lines), encoding="utf-8")

    sh_lines = ["#!/usr/bin/env bash", "set -euo pipefail",
                "# Kräver: railway CLI inloggad och länkad till rätt projekt.",
                "# Kör: bash deploy_kit/railway_set_vars.sh"]
    for k, v in {**secrets_set, **flags}.items():
        # Escape single quotes
        safe = v.replace("'", "'\\''")
        sh_lines.append(f"railway variables set {k}='{safe}'")
    (out_dir / "railway_set_vars.sh").write_text("\n".join(sh_lines) + "\n", encoding="utf-8")
    (out_dir / "railway_set_vars.sh").chmod(0o700)
    (out_dir / "railway_env.txt").chmod(0o600)

    print("✅ deploy_kit/railway_env.txt   (copy-paste till Railway → Variables)")
    print("✅ deploy_kit/railway_set_vars.sh (kör om du har Railway CLI)")
    print()
    print("Krav på din sida:")
    print("  1. Logga in i Railway. Stäng inte projektet.")
    print("  2. Antingen:")
    print("     a) Öppna deploy_kit/railway_env.txt och klistra in de okommenterade raderna i Variables.")
    print("     b) Kör 'bash deploy_kit/railway_set_vars.sh' om CLI är installerad.")
    print("  3. Verifiera att SUPABASE_KEY i Railway är service_role (inte anon).")
    print("  4. Sätt RESTAURANT_UUID=bd525e53-cfb0-4818-a666-90664cd8414f om saknas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
