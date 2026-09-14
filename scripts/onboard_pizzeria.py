#!/usr/bin/env python3
"""
Onboarda en ny pizzeria – hela kedjan i ett kommando.

Gör i ordning:
  1. POST /admin/tenants/onboard  → restaurants-rad (egen UUID), meny i menus, tenant_health
  2. (--create-vapi-assistant)    → klonar Gislegrillen-assistenten i Vapi:
        - genererar system-prompt från menyfilen (namn per kategori)
        - skapar draft_order + place_order med tenantens URL och webhook-secret
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

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from env_loader import load_env_file

load_env_file(ROOT / ".env")

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
    "drycker": "Dryck",
}


def fail(msg: str) -> None:
    print(f"❌ {msg}")
    sys.exit(1)


def build_menu_names(menu: dict) -> str:
    """Generera kompakt lista med kanoniska menynamn utan LLM-styrda id:n."""
    lines = []
    for cat, items in menu.items():
        if not isinstance(items, list) or not items:
            continue
        label = CATEGORY_LABELS.get(cat, cat.capitalize())
        names = ", ".join(
            str(it["name"]).strip()
            for it in items
            if isinstance(it, dict) and str(it.get("name") or "").strip()
        )
        if names:
            lines.append(f"{label}: {names}.")
    return "\n".join(lines)


def build_system_prompt(name: str, menu: dict) -> str:
    """Sätt ihop gemensamma samtalsregler, restaurangens meny och exempel."""
    rules = (ROOT / "voice_conversation_rules.md").read_text(encoding="utf-8")
    examples = (ROOT / "voice_examples.md").read_text(encoding="utf-8")
    return (
        rules.replace("{{RESTAURANT_NAME}}", name).rstrip()
        + "\n\n# Menynamn\n"
        + build_menu_names(menu)
        + "\n\n# Exempel\n"
        + examples.replace("{{RESTAURANT_NAME}}", name).lstrip()
    )


# Function tools reject timeoutSeconds/backoffPlan (Vapi 400). The values
# below are the intended API Request-tool settings from Vapi reliability docs.
TOOL_TIMEOUT_SECONDS = 20
TOOL_BACKOFF_PLAN = {"type": "fixed", "maxRetries": 0, "baseDelaySeconds": 1}
PLACE_ORDER_GOODBYE = "din beställning är klar om tio minuter, en kvart, välkommen"

DRAFT_ORDER_FUNCTION = {
    "name": "draft_order",
    "strict": True,
    "description": (
        "Validera menyn och returnera readback. Anropa när kunden är klar "
        "(nej, inget mer, eller att det är bra). Säg inget extra medan det går. Sparar inte."
    ),
}

PLACE_ORDER_FUNCTION = {
    "name": "place_order",
    "strict": True,
    "description": (
        "Spara ordern efter uppläsning och kundens ja. Inte före. "
        "Säg inget extra medan det går. Framgångsägning kommer bara om backend sparat."
    ),
}

DRAFT_ORDER_MESSAGES = [
    {"type": "request-start", "content": "okej,", "blocking": False},
    {
        "type": "request-response-delayed",
        "content": "det tar en sekund till,",
        "timingMilliseconds": 5000,
    },
    {
        "role": "system",
        "type": "request-complete",
        "content": (
            "läs readback med små bokstäver, en mening, inga frågetecken på namnen, "
            "hoppa över för att ta med, avsluta med är det bra så?"
        ),
    },
    {
        "role": "system",
        "type": "request-failed",
        "content": (
            "fråga bara det som saknas, en sak i taget. gissa inte rätter, "
            "storlekar, drycker eller priser. lova inte att något är sparat."
        ),
    },
]

PLACE_ORDER_MESSAGES = [
    {"type": "request-start", "content": "okej,", "blocking": False},
    {
        "type": "request-response-delayed",
        "content": "det tar en sekund till,",
        "timingMilliseconds": 5000,
    },
    {
        "type": "request-complete",
        "content": PLACE_ORDER_GOODBYE,
        "contents": [{"text": PLACE_ORDER_GOODBYE, "type": "text", "language": "sv"}],
        "endCallAfterSpokenEnabled": True,
    },
    {
        "role": "system",
        "type": "request-failed",
        "content": (
            "läs readback igen med små bokstäver och fråga är det bra så? "
            "lova inte att ordern är sparad. anropa inte endCall."
        ),
    },
]


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
    r = httpx.post(
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
        up = httpx.post(
            f"{base}/admin/menu/upload?rest_id={args.external_id}",
            headers=admin_headers, json=menu, timeout=30,
        )
        if not up.is_success:
            fail(f"Menyuppdatering misslyckades: {up.status_code} {up.text[:300]}")
        print(f"   ✅ Meny uppdaterad (version {up.json().get('version')})")
        onboard = {"vapi_server_url": f"{base}/vapi/webhook?rest_id={args.external_id}"}
    elif not r.is_success:
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
        tpl = httpx.get(f"https://api.vapi.ai/assistant/{TEMPLATE_ASSISTANT_ID}", headers=vh, timeout=20)
        if not tpl.is_success:
            fail(f"Kunde inte läsa mall-assistenten: {tpl.status_code} {tpl.text[:200]}")
        template = tpl.json()

        # Orderverktyg för tenanten (egen URL + secret-header).
        tpl_model = template.get("model") or {}
        tool_ids = tpl_model.get("toolIds") or []
        order_tool_templates = {}
        keep_tool_ids = []
        for tid in tool_ids:
            tr = httpx.get(f"https://api.vapi.ai/tool/{tid}", headers=vh, timeout=20)
            if not tr.is_success:
                continue
            t = tr.json()
            tool_name = (t.get("function") or {}).get("name")
            if tool_name in {"draft_order", "place_order"}:
                order_tool_templates[tool_name] = t
            else:
                keep_tool_ids.append(tid)  # transferCall/endCall är tenant-neutrala
        missing_tools = {"draft_order", "place_order"} - set(order_tool_templates)
        if missing_tools:
            fail(f"Saknar orderverktyg på mall-assistenten: {', '.join(sorted(missing_tools))}")

        new_order_tool_ids = []
        for tool_name in ("draft_order", "place_order"):
            tool_template = order_tool_templates[tool_name]
            function = dict(tool_template["function"])
            if tool_name == "draft_order":
                function["description"] = DRAFT_ORDER_FUNCTION["description"]
                messages = DRAFT_ORDER_MESSAGES
            else:
                function["description"] = PLACE_ORDER_FUNCTION["description"]
                messages = PLACE_ORDER_MESSAGES
            tool_payload = {
                "type": "function",
                "function": function,
                "server": {
                    "url": vapi_server_url,
                    "headers": {"X-Webhook-Secret": WEBHOOK_SHARED_SECRET},
                },
                "async": False,
                "messages": messages,
            }
            # place_order must not copy a confirmation rejectionPlan. A rejected
            # tool call previously made the assistant transfer instead of reading
            # the order back.
            if tool_name != "place_order" and tool_template.get("rejectionPlan"):
                tool_payload["rejectionPlan"] = tool_template["rejectionPlan"]
            nt = httpx.post(
                "https://api.vapi.ai/tool",
                headers=vh,
                timeout=20,
                json=tool_payload,
            )
            if not nt.is_success:
                fail(f"Kunde inte skapa {tool_name}: {nt.status_code} {nt.text[:300]}")
            new_tool_id = nt.json()["id"]
            new_order_tool_ids.append(new_tool_id)
            print(f"   ✅ {tool_name} skapad: {new_tool_id}")

        system_prompt = build_system_prompt(args.name, menu)
        new_model = {
            k: v
            for k, v in tpl_model.items()
            if k
            in (
                "provider",
                "model",
                "temperature",
                "maxTokens",
                "reasoningEffort",
                "promptCacheRetention",
            )
        }
        if new_model.get("promptCacheRetention"):
            new_model["promptCacheKey"] = f"restaurant-order-{args.external_id}"
        new_model["toolIds"] = new_order_tool_ids + keep_tool_ids
        new_model["messages"] = [{"role": "system", "content": system_prompt}]

        payload = {
            "name": f"{args.name} AI",
            "model": new_model,
            "server": {"url": vapi_server_url, "headers": {"X-Webhook-Secret": WEBHOOK_SHARED_SECRET}},
        }
        for k in ("voice", "transcriber", "firstMessage", "firstMessageMode",
                  "silenceTimeoutSeconds", "maxDurationSeconds", "backgroundSound",
                  "stopSpeakingPlan", "startSpeakingPlan", "endCallMessage", "hooks"):
            if template.get(k) is not None:
                payload[k] = template[k]
        payload["firstMessage"] = f"välkommen till {args.name}, vad vill du beställa?"
        ssp = dict(payload.get("stopSpeakingPlan") or {})
        ssp["acknowledgementPhrases"] = []
        payload["stopSpeakingPlan"] = ssp

        na = httpx.post("https://api.vapi.ai/assistant", headers=vh, json=payload, timeout=30)
        if not na.is_success:
            fail(f"Kunde inte skapa assistent: {na.status_code} {na.text[:400]}")
        assistant_id = na.json()["id"]
        print(f"   ✅ Assistent skapad: {assistant_id} ('{args.name} AI')")
        print("   ⚠️  Granska system-prompten i Vapi-dashboarden och koppla pizzerians telefonnummer!")
    else:
        print("2/3 (hoppades över – kör med --create-vapi-assistant för att klona Vapi-assistenten)")

    # ---- 3. Preflight ----
    print("3/3 Preflight-kontroll ...")
    pf = httpx.get(
        f"{base}/admin/tenants/{args.external_id}/preflight",
        headers={"X-Admin-Key": ADMIN_SECRET}, timeout=20,
    )
    if not pf.is_success:
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
