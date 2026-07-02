# Gislegrillen Voice AI Order System – Projektkontext

**Syfte:** Ge en ny chatt full kontext om vad projektet är, vilka filer som finns och
hur allt hänger ihop. Läs denna fil först när du hjälper till i projektet.

---

## Vad projektet är

En **multi-tenant röst-AI för pizzerior** som tar emot beställningar via telefon:

1. **Vapi.ai** svarar i telefon, pratar svenska, tar beställningen och anropar backend.
2. **Backend** (FastAPI, `main.py`, deployad på Railway) validerar mot menyn, skriver
   ordern till Supabase (system of record) och köar SMS-bekräftelse via Vonage.
3. **Lovable/KDS** läser ordrar från Supabase och visar dem i köket.
4. **Ops-agent + worker** sköter drift autonomt (SMS-retries, incidenter, tenant-paus,
   städning). En extern GitHub Actions-watchdog övervakar utifrån.

Varje pizzeria är en **tenant** med egen `restaurant_uuid`, egen meny, egen SMS-branding
och egen Vapi-assistent. Ingenting delas mellan pizzerior.

**Inga priser:** Prissättning är medvetet borttagen ur meny och flöde – betalning sker
på plats. AI:n frågar aldrig självmant om modifierare (storlek, gluten, sås osv.); den
lägger bara till det kunden själv nämner, som fri text i `special_requests`.

Produktion: `https://web-production-a9a48.up.railway.app`. GitHub:
`william6888/swedenvoice-platform` (branch `main`, skyddad – ändringar via PR).
Supabase-projekt: `zgllqocecavcgctbduip`.

---

## Kodfiler (system of record)

| Fil | Roll |
|-----|------|
| **main.py** | FastAPI-app. Webhook `/vapi/webhook`, `/place_order`, `/draft_order`, `/orders`, `/menu`, `/update_order_status`, `/dashboard`, `/system_prompt`, `/health` (visar `build`-tagg). Admin: `/admin/ops/run`, `/admin/menu/upload`, `/admin/tenants/onboard`, `/admin/tenants/{rest_id}/preflight`. Larmkanal (`_send_operator_alert`, i tråd), samtalstillstånd i `call_state`, webhook-secret från env eller `ops_settings`. |
| **order_integrity.py** | Pure-funktioner: canonical payload, payload_hash, idempotency-key, validering. |
| **order_service.py** | Supabase-lager: `idempotency_records`, `order_events`, tenant-scopad fetch/update av `orders`. Soft-fail om migration saknas. |
| **ops_agent.py** | Policy-styrd autonom drift: `incidents`, `ops_actions`, `tenant_health` pausa/återuppta, `queue_sms_job`, `alert_operator`. Bara säkra åtgärder. Larmkanal injiceras av main.py. |
| **ops_worker.py** | `run_tick`: SMS-retry, dead-letter, tenant_health-reconcile, idempotency-cleanup, auto-resolve gamla P2/P3-incidenter, `call_state`-cleanup. |
| **confirmation.py** | HMAC-signerade draft-tokens + verbal readback (TTL 5 min). |
| **menu_match.py** | Menymatchning (id/exact/alias/fuzzy) mot tenantens meny. |
| **index.html** | Köksdashboard (XSS-säker), läser via `/orders`. |
| **menu.json** | Gislegrillens meny (kategorier → listor med `id`, `name`, `aliases`, `description`). Inga priser. `_meta` = referensdata (modifierare/gluten). |
| **system_prompt.md** | AI-personlighet/flöde för Vapi (opt-in-modifierare, äta här/ta med, inga priser). ID-kartan matchar `menu.json`. |
| **test_system.py** | Röktest som CI kör (inga externa tjänster). |
| **tests/** | Pytest-svit (109 tester): order_integrity, menu_match, draft-flöde, idempotency/commit, ops_agent, ops_worker, sms-format, m.m. |
| **scripts/onboard_pizzeria.py** | Onboarda ny pizzeria i ett kommando (backend + Vapi-assistentkloning + preflight). |
| **scripts/** | Övriga hjälpskript: `go_live_verify.py`, `generate_secrets.py`, `setup_webhook_auth.py`, `set_railway_vonage_vars.py`, `smoke_test_fas2.py`. |

## Infrastruktur / konfig

| Fil | Roll |
|-----|------|
| **Procfile / railway.json / runtime.txt / .python-version** | Railway-bygge (Python 3.11, uvicorn, `/health`-healthcheck). |
| **.github/workflows/python-checks.yml** | CI: compileall + `test_system.py` + `pytest tests`. |
| **.github/workflows/watchdog.yml** | Extern watchdog var 15 min: pingar `/health`, SMS vid nere, backup-ops-tick. |
| **.github/workflows/trufflehog.yml** | Secret-scanning. |
| **.env / .env.template** | Nycklar: `VAPI_API_KEY`, `VONAGE_*`, `SUPABASE_URL/KEY` (service_role), `ADMIN_SECRET`, `WEBHOOK_SHARED_SECRET`, `DRAFT_SIGNING_SECRET`, `ENCRYPTION_SECRET`, `RESTAURANT_UUID`, ops-flaggor. `.env` committas aldrig. |
| **`supabase_*.sql`** | Historik över DB-migrationer (schema-referens). |

## Dokumentation

| Fil | Innehåll |
|-----|----------|
| **README.md** | Översikt, setup, endpoints. |
| **ONBOARDING_NY_PIZZERIA.md** | Körschema för ny pizzeria + isoleringsgarantier. |
| **LOVABLE_SAKER_INLOGGNING.md** | Hur anon-läsning stängs / Lovable-inloggning + `restaurant_members`. |
| **RAILWAY_GUIDE.md** | Deploy till Railway. |
| **VAPI_SETUP_GUIDE.md** | Vapi Assistant, Tool `place_order`, webhook, telefonnummer. |
| **MULTI_PIZZERIA.md** | Multi-tenant-översikt. |

---

## Supabase-tabeller (viktigast)

- **orders** – ordrar (system of record för KDS). RLS: `member_select_orders` / `member_update_orders` (via `restaurant_members`). Anon-läsning borttagen; Lovable läser via edge-funktioner med service_role.
- **restaurants** – tenants (`external_id`, `name`, `contact_phone`, throttle, `deleted_at`).
- **restaurant_members** – kopplar `auth.users` → `restaurant_id` för inloggad KDS.
- **menus** – per-tenant meny (`restaurant_uuid` → `menu_json`, `version`). Backend läser härifrån före fil.
- **call_state** – samtalstillstånd (call_id → tenant/telefon/draft) så pågående samtal överlever deploy.
- **ops_settings** – plattformsinställningar (`owner_alert_phone`, `webhook_shared_secret`, `alert_webhook_url`).
- **sms_jobs, incidents, ops_actions, tenant_health, idempotency_records, order_events, restaurant_secrets** – drift/autonomi/integritet.

Backend använder **service_role**-nyckeln (går förbi RLS). Sätt den i Railway som `SUPABASE_KEY`.

---

## Onboarda ny pizzeria (kort)

```bash
python3 scripts/onboard_pizzeria.py \
  --external-id PizzeriaRoma_01 --name "Pizzeria Roma" \
  --contact-phone +46701234567 --menu-file menu_pizzeria_roma.json \
  --create-vapi-assistant
```

Sedan manuellt: koppla telefonnummer i Vapi + skapa Lovable-inloggning
(`restaurant_members`). Verifiera med `GET /admin/tenants/{id}/preflight`. Fullständigt
körschema i **ONBOARDING_NY_PIZZERIA.md**.

---

## När du hjälper i en ny chatt

- Använd denna fil som källa till sanning för omfattning, filer och flöde.
- API-nycklar committas **aldrig** (`.env` är i `.gitignore`).
- `main` är skyddad – gör ändringar via branch + PR (CI måste vara grön).
- Bumpa `BUILD_TAG` i `main.py` vid deploy så `/health` visar rätt version.
- Bevis före ändring: läs Supabase/Vapi/loggar hellre än att gissa.
