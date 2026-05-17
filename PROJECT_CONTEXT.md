# Gislegrillen Order System – Projektkontext för AI/Chatt

**Syfte:** Denna fil ger full kontext till en ny chatt så att den vet exakt vad projektet är, vilka filer som finns, vad som byggts och hur allt ska fungera. Läs denna fil först när du hjälper till i detta projekt.

---

## Referens (från tidigare chatt)

- **Branch:** `cursor/gislegrillen-order-system-1e1d`
- **Base branch:** `cursor/gislegrillen-order-system-1e1d`
- **Request ID (referens):** `bc-412647da-b66e-43b9-8da5-bc2bb78c8b06`

---

## Vad projektet är

**Gislegrillen Voice AI Order System** – Ett beställningssystem för pizzeria som:

1. **Tar emot samtal** via Vapi.ai (röst-AI som svarar på telefon).
2. **AI:en** (konfigurerad i Vapi – t.ex. LLM/röst) pratar svenska, tar beställningar, bekräftar och anropar backend.
3. **Backend** (FastAPI i `main.py`) tar emot beställningar från Vapi, sparar i `orders.json`, skriver köksbong till konsolen/loggar, kan skicka SMS (Vonage) och skriva till Supabase.
4. **Dashboard** (`index.html`) visar beställningar i köket med status (pending/ready/completed).

Allt byggt, testat och dokumenterat. API-nycklar och känslig konfiguration ligger i `.env` (kopiera från `.env.template`).

---

## Viktiga filer (översikt)

| Fil | Roll |
|-----|------|
| **main.py** | FastAPI-app: `/place_order`, `/draft_order`, `/orders`, `/menu`, `/update_order_status`, `/dashboard`, `/vapi/webhook`, `/system_prompt`, `/health`, `/admin/ops/run`, `/admin/ops/incidents`. Använder `order_integrity` + `order_service` så Supabase är system of record (ingen falsk ordersuccess). |
| **order_integrity.py** | Pure-funktioner: canonical payload, payload_hash, idempotency-key, validering (quantity, status enum, special_request maxlängd, id/name invariant). |
| **order_service.py** | Supabase-lagret: `idempotency_records`, `order_events`, tenant-scoped fetch/update av `orders`. Soft-fails om migrationen ej är körd. |
| **ops_agent.py** | Policy-styrd autonom drift: `incidents`, `ops_actions`, tenant_health pause/resume, queue_sms_job. Bara säkra åtgärder tillåts. |
| **ops_worker.py** | Tick-funktion (`run_tick`) som retryar SMS, dead-letterar efter max-attempts, reconcilar tenant_health och rensar gamla idempotency-rader. |
| **confirmation.py** | HMAC-signerade draft-tokens + canonical readback. Används av `/draft_order` och verifieras i place_order. |
| **index.html** | Köksdashboard – XSS-säker (`escapeHtml`), läser från Supabase via `/orders`, hanterar `needs_review`-status. |
| **menu.json** | Meny (pizzor, kebabs, burgare, tillbehör, drycker) med id, namn, pris, beskrivning. |
| **orders.json** | Sparade beställningar (persistent). |
| **system_prompt.md** | AI-personlighet för Vapi – svenska, beställningsflöde, när verktyget `place_order` ska anropas. Kopieras till Vapi Assistant. |
| **.env** | API-nycklar: `VAPI_API_KEY`, Vonage (`VONAGE_*`), Supabase (`SUPABASE_URL`, `SUPABASE_KEY`), valfritt `ADMIN_SECRET`, `WEBHOOK_SHARED_SECRET`. Optional: `HOST`, `PORT`. |
| **.env.template** | Mall för .env (inga riktiga nycklar). |
| **requirements.txt** | Python-beroenden (fastapi, uvicorn, pydantic, requests, python-dotenv). |
| **start_server.sh** | Startar servern lokalt (t.ex. `python main.py` / uvicorn). |
| **Procfile** | Railway startkommando. Backend deployas till Railway. |
| **test_system.py** | Test av endpoints och att nödvändiga env-variabler finns. |

### Dokumentation (redan skapad)

| Fil | Innehåll |
|-----|----------|
| **README.md** | Översikt, setup, endpoints. |
| **QUICKSTART.md** | Snabbstart på engelska. |
| **VAPI_SETUP_GUIDE.md** | Steg-för-steg Vapi: Assistant, Voice (ElevenLabs Jonas / Cartesia för låg latens), Tool `place_order`, webhook, telefonnummer. Inkl. felsökning dålig svenska/robotröst. |
| **VAPI_PLACE_ORDER_OCH_SERVER_URL.md** | Ska `place_order` peka på Railway? Tool vs assistant server URL, timeouts, kallstart, idempotency – checklista och risker (stämmer med Vapis egen varningslista). |
| **WEBHOOK_AUTH_SETUP.md** | `WEBHOOK_SHARED_SECRET`: säkra POST `/place_order` och `/vapi/webhook` med header/Bearer; tom = öppet (bakåtkompatibelt). |
| **ENKEL_WEBHOOK_AUTH.md** | Kort 3-stegsguide; kör `python3 scripts/setup_webhook_auth.py` för färdig text till Railway + Vapi. |
| **KOMPLETT_GUIDE.md** | Komplett svensk guide: Railway, .env, Vapi, Tool-schema, röst (ElevenLabs/Cartesia), felsökning. |
| **RAILWAY_GUIDE.md** | Steg-för-steg: deploya till Railway, Vapi-URL. |
| **STARTA_SYSTEMET.md** | Starta systemet på svenska. |
| **SNABBSTART.txt** | Kort snabbstart. |
| **NUVARANDE_STATUS.md** | Status (t.ex. väntar på Vapi-nyckel). |
| **PROJECT_SUMMARY.txt** | Sammanfattning av levererat (filstruktur, features, hur man kör). |
| **ONBOARDING_NY_PIZZERIA.md** | Steg-för-steg checklista för att lägga till en ny pizzeria/restaurang (Supabase, meny, Vapi, alla verktyg). |
| **GO_LIVE_GATES.md** | Krävda gates innan extern försäljning: migrationer, tester, konfig, manuella livtester, rollback-plan. |
| **LIVE_READINESS_AUDIT.md** | Hela audit-rapporten: P0/P1-risker, konkurrentanalys, målarkitektur, implementationsplan. |
| **PHASE1_ORDER_INTEGRITY_SPEC.md** | Teknisk spec för Fas 1 – idempotency, Supabase som SoR, validering. Implementerad. |
| **supabase_phase1_order_integrity.sql** | Idempotent migration för Fas 1: nya kolumner på orders + nya tabeller (order_events, idempotency_records, incidents, ops_actions, sms_jobs, tenant_health). RLS bara på nya tabellerna – Lovable's anon SELECT på orders rörs INTE. |
| **tests/** | Pytest-svit: order_integrity, id/name invariant, status enum, draft tokens, FakeSupabase-baserade idempotency- och commit-tester, ops-agent och ops-worker. |
| **PROBLEM_OCH_ATgarder.md** | Nuvarande problem, vad ändringar orsakat, åtgärder. Backend är tolerant (fallback vid saknad kolumn; startvarning vid RLS/anon). |
| **SUPABASE_ADD_SPECIAL_INSTRUCTIONS.sql** | Kör en gång i Supabase: lägger till kolumnen special_instructions i orders. |

---

## Teknisk stack

- **Backend:** Python 3, FastAPI, uvicorn, pydantic, requests, python-dotenv.
- **Voice/LLM:** Vapi.ai (telefon + röst + styrning av samtal); LLM och röst väljs i Vapi-dashboarden.
- **Röst:** ElevenLabs med Jonas (svenska) eller Cartesia för lägre latens; undvik Vapis egna röster för svenska.
- **SMS:** Vonage (orderbekräftelse till kund när telefon finns i webhook).
- **Frontend:** Vanilla HTML/CSS/JS (Bootstrap 5) för dashboard.

---

## Så här kör du systemet

1. `pip install -r requirements.txt`
2. `cp .env.template .env` och fyll i API-nycklar.
3. Starta backend: `python main.py` (eller `./start_server.sh`).
4. Deploya till Railway (se RAILWAY_GUIDE.md). Sätt Vapi Server URL till `https://<railway-url>/vapi/webhook`.
5. Öppna dashboard: `http://localhost:8000/dashboard`.

---

## Vapi-konfiguration (påminnelse)

- **Tool:** `place_order`, POST, URL = din publika URL + `/place_order`. Schema: `items` (array med `id`, `name`, `quantity`), `special_requests` (string, optional).
- **System prompt:** Kopiera hela innehållet från `system_prompt.md` till Vapi Assistant.
- **Röst:** ElevenLabs + Jonas (Voice ID `e6OiUVixGLmvtdn2GJYE`) eller Cartesia + svensk röst för lägre latens. Språk: Swedish (sv-SE).

---

## Supabase (KDS / multi-tenant)

- **Railway:** Sätt `SUPABASE_KEY` till **service_role**-nyckeln (inte anon), annars kan backend inte läsa `restaurants` efter RLS. Vid start varnar appen om restaurants returnerar 0 rader.
- **special_instructions:** Kör en gång i Supabase SQL Editor: `ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS special_instructions text;` (fil: `SUPABASE_ADD_SPECIAL_INSTRUCTIONS.sql`). Om kolumnen saknas sparar backend order ändå (fallback utan fältet).
- **Problem och åtgärder:** Se PROBLEM_OCH_ATgarder.md.

---

## När du hjälper i en ny chatt

- Använd denna fil som **källa till sanning** för projektets omfattning, filer och flöde.
- Ändra bara filer som nämns här (eller lägg till nya om användaren vill utöka systemet).
- API-nycklar ska **aldrig** committas; de finns i `.env` (och .env är i .gitignore).
- Vid problem med Railway, Vapi eller .env: utgå från att all konfiguration beskrivs i RAILWAY_GUIDE.md, KOMPLETT_GUIDE.md och VAPI_SETUP_GUIDE.md.

Om något verkar saknas eller avvika från denna beskrivning, fråga användaren eller läs den aktuella filen i repot.
