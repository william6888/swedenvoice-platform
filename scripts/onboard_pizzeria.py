#!/usr/bin/env python3
"""
Onboarda en ny pizzeria – hela kedjan i ett kommando.

Gör i ordning:
  1. POST /admin/tenants/onboard  → restaurants-rad (egen UUID), meny i menus, tenant_health
  2. (--create-vapi-assistant)    → klonar Gislegrillen-assistenten i Vapi:
        - genererar system-prompt från menyfilen (namn + ID-karta per kategori)
        - skapar place_order-tool med tenantens serverUrl + X-Webhook-Secret
        - skapar assistent med samma modell/röst men tenantens namn och prompt
  3. GET /admin/tenants/{rest_id}/preflight → verifierar att allt är grönt

Användning:
  python3 scripts/onboard_pizzeria.py \
      --external-id PizzeriaRoma_01 \
      --name "Pizzeria Roma" \
      --contact-phone +46701234567 \
      --menu-file menu_pizzeria_roma.json \
      --create-vapi-assistant

Kvar att göra manuellt efteråt (kan inte automatiseras via API):
  - Koppla pizzerians telefonnummer till den nya assistenten i Vapi-dashboarden.
  - Skapa Lovable-inloggning + rad i restaurant_members (LOVABLE_SAKER_INLOGGNING.md).
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

BACKEND_URL = os.getenv("BACKEND_URL", "https://web-production-a9a48.up.railway.app").rstrip("/")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
VAPI_API_KEY = os.getenv("VAPI_API_KEY", "")
WEBHOOK_SHARED_SECRET = os.getenv("WEBHOOK_SHARED_SECRET", "")
TEMPLATE_ASSISTANT_ID = os.getenv("VAPI_TEMPLATE_ASSISTANT_ID", "a28aec7f-4dcc-4b88-a5b1-02f594c878d9")

CATEGORY_LABELS = {
    "pizzas": "Pizzor",
    "kebabs": "Kebab",
    "kyckling": "Kyckling",
    "sallader": "Sallader",
    "hamburgare": "Hamburgare",
    "korv": "Korv",
    "ovrigt": "Övrigt",
    "tillbehor": "Tillbehör",
}


def fail(msg: str) -> None:
    print(f"❌ {msg}")
    sys.exit(1)


def build_id_map(menu: dict) -> str:
    """Generera ID-kartan för system-prompten från meny-JSON."""
    lines = []
    for cat, items in menu.items():
        if not isinstance(items, list) or not items:
            continue
        label = CATEGORY_LABELS.get(cat, cat.capitalize())
        pairs = ", ".join(f"{it['name']}={it['id']}" for it in items if isinstance(it, dict) and it.get("id") is not None)
        if pairs:
            lines.append(f"{label}: {pairs}.")
    return "\n".join(lines)


def build_system_prompt(name: str, menu: dict) -> str:
    """Bygg tenantens system-prompt från Gislegrillen-mallen: byt namn + ID-karta."""
    template = (ROOT / "system_prompt.md").read_text(encoding="utf-8")
    # Byt varumärke i personlighetsraden.
    prompt = template.replace("Gislegrillen", name)
    # Ersätt ID-kartan (allt efter "Använd rätt id från menyn:") med tenantens egna.
    marker = "Använd rätt id från menyn:"
    if marker in prompt:
        head = prompt.split(marker)[0]
        prompt = head + marker + "\n" + build_id_map(menu) + "\n"
    return prompt


def main() -> None:
    p = argparse.ArgumentParser(description="Onboarda ny pizzeria")
    p.add_argument("--external-id", required=True, help="T.ex. PizzeriaRoma_01 (unik tenant-nyckel)")
    p.add_argument("--name", required=True, help="Visningsnamn i kundens SMS, t.ex. 'Pizzeria Roma'")
    p.add_argument("--contact-phone", required=True, help="Pizzerians nummer i SMS-footern, +46...")
    p.add_argument("--menu-file", required=True, help="Meny-JSON i samma format som menu.json")
    p.add_argument("--create-vapi-assistant", action="store_true", help="Klona Vapi-assistent för tenanten")
    p.add_argument("--backend-url", default=BACKEND_URL)
    args = p.parse_args()

    if not ADMIN_SECRET:
        fail("ADMIN_SECRET saknas i .env")
    menu_path = Path(args.menu_file)
    if not menu_path.exists():
        fail(f"Menyfilen finns inte: {menu_path}")
    menu = json.loads(menu_path.read_text(encoding="utf-8"))

    base = args.backend_url.rstrip("/")
    admin_headers = {"X-Admin-Key": ADMIN_SECRET, "Content-Type": "application/json"}

    # ---- 1. Onboard i backend/Supabase ----
    print(f"1/3 Onboardar {args.external_id} i {base} ...")
    r = requests.post(
        f"{base}/admin/tenants/onboard",
        headers=admin_headers,
        json={
            "external_id": args.external_id,
            "name": args.name,
            "contact_phone": args.contact_phone,
            "menu": menu,
        },
        timeout=30,
    )
    if r.status_code == 409:
        print("   ℹ️  Tenanten finns redan – fortsätter med befintlig (menyn uppdateras separat).")
        up = requests.post(
            f"{base}/admin/menu/upload?rest_id={args.external_id}",
            headers=admin_headers, json=menu, timeout=30,
        )
        if not up.ok:
            fail(f"Menyuppdatering misslyckades: {up.status_code} {up.text[:300]}")
        print(f"   ✅ Meny uppdaterad (version {up.json().get('version')})")
        onboard = {"vapi_server_url": f"{base}/vapi/webhook?rest_id={args.external_id}"}
    elif not r.ok:
        fail(f"Onboarding misslyckades: {r.status_code} {r.text[:300]}")
    else:
        onboard = r.json()
        print(f"   ✅ Restaurang skapad: uuid={onboard.get('restaurant_uuid')} meny={onboard.get('menu_items')} artiklar")

    vapi_server_url = onboard["vapi_server_url"]

    # ---- 2. Vapi-assistent ----
    if args.create_vapi_assistant:
        if not VAPI_API_KEY:
            fail("VAPI_API_KEY saknas i .env")
        if not WEBHOOK_SHARED_SECRET:
            fail("WEBHOOK_SHARED_SECRET saknas i .env (behövs för tool-headern)")
        vh = {"Authorization": f"Bearer {VAPI_API_KEY}", "Content-Type": "application/json"}

        print("2/3 Klonar Vapi-assistent ...")
        tpl = requests.get(f"https://api.vapi.ai/assistant/{TEMPLATE_ASSISTANT_ID}", headers=vh, timeout=20)
        if not tpl.ok:
            fail(f"Kunde inte läsa mall-assistenten: {tpl.status_code} {tpl.text[:200]}")
        template = tpl.json()

        # place_order-tool för tenanten (egen URL + secret-header).
        tpl_model = template.get("model") or {}
        tool_ids = tpl_model.get("toolIds") or []
        place_order_schema = None
        keep_tool_ids = []
        for tid in tool_ids:
            tr = requests.get(f"https://api.vapi.ai/tool/{tid}", headers=vh, timeout=20)
            if not tr.ok:
                continue
            t = tr.json()
            if (t.get("function") or {}).get("name") == "place_order":
                place_order_schema = t.get("function")
            else:
                keep_tool_ids.append(tid)  # transferCall/endCall är tenant-neutrala
        if not place_order_schema:
            fail("Hittade ingen place_order-tool på mall-assistenten")

        nt = requests.post(
            "https://api.vapi.ai/tool", headers=vh, timeout=20,
            json={
                "type": "function",
                "function": place_order_schema,
                "server": {"url": vapi_server_url, "headers": {"X-Webhook-Secret": WEBHOOK_SHARED_SECRET}},
            },
        )
        if not nt.ok:
            fail(f"Kunde inte skapa place_order-tool: {nt.status_code} {nt.text[:300]}")
        new_tool_id = nt.json()["id"]
        print(f"   ✅ place_order-tool skapad: {new_tool_id}")

        system_prompt = build_system_prompt(args.name, menu)
        new_model = {k: v for k, v in tpl_model.items() if k in ("provider", "model", "temperature", "maxTokens")}
        new_model["toolIds"] = [new_tool_id] + keep_tool_ids
        new_model["messages"] = [{"role": "system", "content": system_prompt}]

        payload = {
            "name": f"{args.name} AI",
            "model": new_model,
            "server": {"url": vapi_server_url, "headers": {"X-Webhook-Secret": WEBHOOK_SHARED_SECRET}},
        }
        for k in ("voice", "transcriber", "firstMessage", "firstMessageMode",
                  "silenceTimeoutSeconds", "maxDurationSeconds", "backgroundSound",
                  "stopSpeakingPlan", "startSpeakingPlan"):
            if template.get(k) is not None:
                payload[k] = template[k]

        na = requests.post("https://api.vapi.ai/assistant", headers=vh, json=payload, timeout=30)
        if not na.ok:
            fail(f"Kunde inte skapa assistent: {na.status_code} {na.text[:400]}")
        assistant_id = na.json()["id"]
        print(f"   ✅ Assistent skapad: {assistant_id} ('{args.name} AI')")
        print("   ⚠️  Granska system-prompten i Vapi-dashboarden och koppla pizzerians telefonnummer!")
    else:
        print("2/3 (hoppades över – kör med --create-vapi-assistant för att klona Vapi-assistenten)")

    # ---- 3. Preflight ----
    print("3/3 Preflight-kontroll ...")
    pf = requests.get(
        f"{base}/admin/tenants/{args.external_id}/preflight",
        headers={"X-Admin-Key": ADMIN_SECRET}, timeout=20,
    )
    if not pf.ok:
        fail(f"Preflight misslyckades: {pf.status_code} {pf.text[:300]}")
    result = pf.json()
    for check, value in result["checks"].items():
        mark = "✅" if value is True else ("❌" if value is False else "ℹ️ ")
        print(f"   {mark} {check}: {value}")
    print()
    if result["ready"]:
        print(f"🎉 {args.external_id} är REDO. Kvar manuellt: telefonnummer i Vapi + Lovable-inloggning.")
    else:
        print("⚠️  Inte redo än – åtgärda ❌-raderna ovan innan go-live.")


if __name__ == "__main__":
    main()
