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
| **main.py** | FastAPI-app. Webhook `/vapi/webhook`, `/place_order`, `/draft_order`, `/orders`, `/menu`, `/update_order_status`, `/dashboard`, `/system_prompt`, `/health` (visar `build`-tagg). Lokal `/dashboard`, `/orders` och statusändring kräver signerad HttpOnly-session via `/dashboard/login` (nyckel `DASHBOARD_ACCESS_KEY`, fallback `ADMIN_SECRET`). Okända tenants failar stängt och får aldrig defaultmeny. Admin: `/admin/ops/run`, `/admin/menu/upload`, `/admin/tenants/onboard`, `/admin/tenants/{rest_id}/preflight`. |
| **order_integrity.py** | Pure-funktioner: canonical payload, payload_hash, idempotency-key, validering. |
| **order_service.py** | Supabase-lager: `idempotency_records`, `order_events`, tenant-scopad fetch/update av `orders`. Soft-fail om migration saknas. |
| **ops_agent.py** | Policy-styrd autonom drift: `incidents`, `ops_actions`, `tenant_health` pausa/återuppta, `queue_sms_job`, `alert_operator`. Bara säkra åtgärder. Larmkanal injiceras av main.py. |
| **ops_worker.py** | `run_tick`: SMS-retry, dead-letter, tenant_health-reconcile, idempotency-cleanup, auto-resolve gamla P2/P3-incidenter, `call_state`-cleanup och verifierad dagsbackup. |
| **backup_core.py** | Fail-closed export av 13 tabeller, keyset-paginering, manifest, Fernet-kryptering och upload→download-verifiering. Ett enda tabellfel stoppar hela backupen. |
| **scripts/backup_supabase.py / restore_backup.py** | Skapar/verifierar backup respektive inspekterar eller återställer en explicit tabell. Gamla format-v1-filer stöds. |
| **confirmation.py** | HMAC-signerade draft-tokens + verbal readback (TTL 5 min). |
| **menu_match.py** | Menymatchning (id/exact/alias/fuzzy) mot tenantens meny. |
| **index.html** | Köksdashboard (XSS-säker), läser via `/orders`. |
| **menu.json** | Gislegrillens meny (kategorier → listor med `id`, `name`, `aliases`, `description`). Inga priser. `_meta` = referensdata (modifierare/gluten). |
| **system_prompt.md** | Gislegrillens sammansatta Vapi-prompt (regler + meny + exempel). |
| **voice_conversation_rules.md** | Gemensamma samtalsregler för alla restauranger (`{{RESTAURANT_NAME}}`). |
| **voice_examples.md** | Gemensamma kassa-exempel. |
| **test_system.py** | Röktest som CI kör (inga externa tjänster). |
| **env_loader.py** | Minimal read-only `.env`-läsare. Ersätter `python-dotenv` så runtime inte har dess muterande `set_key`-yta. |
| **tests/** | Pytest-svit (129 tester): order_integrity, menu_match, draft-flöde, idempotency/commit, API/tenant-auth, env-loader, ops_agent, ops_worker, backup/restore, sms-format, m.m. Testerna isolerar alltid live-Supabase. |
| **scripts/onboard_pizzeria.py** | Onboarda ny pizzeria i ett kommando (backend + Vapi-assistentkloning + preflight). |
| **scripts/** | Övriga hjälpskript: `go_live_verify.py`, `generate_secrets.py`, `setup_webhook_auth.py`, `set_railway_vonage_vars.py`, `smoke_test_fas2.py`. |

## Infrastruktur / konfig

| Fil | Roll |
|-----|------|
| **Procfile / railway.json / runtime.txt / .python-version** | Railway-bygge (Python 3.11, uvicorn, `/health`-healthcheck). |
| **.github/workflows/python-checks.yml** | CI: compileall + `test_system.py` + `pytest tests`. |
| **.github/workflows/watchdog.yml** | Extern gratis-watchdog: pingar `/health`, validerar `/admin/ops/run` och misslyckas med GitHub-mail vid verkligt fel. Schemat begär var 15:e minut men GitHub free kan försena/hoppa över körningar; Railway-loopen är primär. |
| **.github/workflows/backup.yml** | Sekundär off-site-backup i GitHub Artifact (90 dagar). Skapar, dekrypterar och strukturvaliderar filen före upload. |
| **.github/workflows/trufflehog.yml** | Secret-scanning. |
| **.env / .env.template** | Nycklar: `VAPI_API_KEY`, `VONAGE_*`, `SUPABASE_URL/KEY` (service_role), `ADMIN_SECRET`, valfri `DASHBOARD_ACCESS_KEY`, `CORS_ALLOWED_ORIGINS`, `WEBHOOK_SHARED_SECRET`, `DRAFT_SIGNING_SECRET`, `ENCRYPTION_SECRET`, `BACKUP_ENCRYPTION_KEY`, `RESTAURANT_UUID`, ops-flaggor. `.env` committas aldrig. HTTP-klient är `httpx`; `requests`/`python-dotenv` är borttagna ur manifests. |
| **`supabase_*.sql`, `supabase/migrations/`** | Historik över DB-migrationer och deployade säkerhetsändringar. |

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

- **orders** – ordrar (system of record för KDS). RLS: `member_select_orders` / `member_update_orders` (via `restaurant_members`). **`anon_select_on_orders` finns fortfarande medvetet** eftersom nuvarande Lovable-dashboard använder anon; ta inte bort den förrän stegen i `LOVABLE_SAKER_INLOGGNING.md` är genomförda.
- **restaurants** – tenants (`external_id`, `name`, `contact_phone`, throttle, `deleted_at`).
- **restaurant_members** – kopplar `auth.users` → `restaurant_id` för inloggad KDS. Klienter får bara läsa sitt eget medlemskap; INSERT/UPDATE/DELETE görs med betrodd service-role så användaren inte kan välja tenant själv.
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

## Kundapp (Lovable, inte köket)

Live: `https://gislegrillen.lovable.app` — projekt `0200f18e-bc5f-468c-a067-cd05dbf0d446`.
Köket är `https://swedenvoice.lovable.app` och rörs inte.

API (`main.py` `/app/*`, `app_channel.py`, `app_prices.py`):
- `GET /app/info`, `GET /app/menu`, `POST /app/otp/request|verify`, `POST /app/orders`, `POST /app/privacy/delete`
- Session TTL 7 dagar. OTP i tabellen `app_otp` (service_role). Reviewer: `APP_REVIEW_PHONE` + `APP_REVIEW_CODE` (Railway-env, inget SMS).
- Extra sås (101): Liten 10 / Stor 18. `pizza_botten` heter **Botten**. `kebabtyp` bara på rätter med kebabkött.
- Rätter utan Qopla-pris döljs i kundmenyn och nekas på `/app/orders`.
- App-SMS: ordernummer, totalt, “Betala på plats.”

## App Store (förberett, inte inlämnat)

Kostar 99 USD/år — görs **inte** nu. PWA räcker som hemskärms-app (Safari Dela → Lägg till på hemskärmen).

Kvar den dagen ni lämnar in:
- Apple Developer i Gislegrillens/företagets namn (org kräver D-U-N-S).
- Capacitor/Median-binär + Xcode + PrivacyInfo.xcprivacy. En URL går inte att ladda upp (guideline 4.2).
- Native värde utöver Safari: APNs-push, offline (finns redan), ev. tabbar/widget.
- App Store Connect: integritetspolicy-URL (`/integritet`), nutrition labels, svenska+engelska screenshots (6.7"/6.5"/iPad), support-URL, åldersgräns, review notes med `APP_REVIEW_PHONE`/`APP_REVIEW_CODE`.
- 5.1.1(v) radering i appen (finns). 3.1.3(e) mat = inte IAP; betala på plats är tillåtet.
- Ingen Google Play i v1. Ingen Lovable-badge.

## När du hjälper i en ny chatt

- Använd denna fil som källa till sanning för omfattning, filer och flöde.
- API-nycklar committas **aldrig** (`.env` är i `.gitignore`).
- `main` är skyddad – gör ändringar via branch + PR (CI måste vara grön).
- Bumpa `BUILD_TAG` i `main.py` vid deploy så `/health` visar rätt version.
- Bevis före ändring: läs Supabase/Vapi/loggar hellre än att gissa.
