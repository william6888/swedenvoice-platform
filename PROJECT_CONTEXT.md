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
2. **AI:en** (Groq/Llama) pratar svenska, tar beställningar, bekräftar och anropar backend.
3. **Backend** (FastAPI i `main.py`) tar emot beställningar från Vapi, sparar i `orders.json`, skickar Pushover-notis, skriver köksbong till konsolen.
4. **Dashboard** (`index.html`) visar beställningar i köket med status (pending/ready/completed).

Allt byggt, testat och dokumenterat. API-nycklar och känslig konfiguration ligger i `.env` (kopiera från `.env.template`).

---

## Viktiga filer (översikt)

| Fil | Roll |
|-----|------|
| **main.py** | FastAPI-app: `/place_order`, `/orders`, `/menu`, `/update_order_status`, `/dashboard`, `/vapi/webhook`, `/system_prompt`, `/health`. CORS, Pushover, köksbong-utskrift. |
| **index.html** | Köksdashboard – Bootstrap 5, orderkort, statusuppdatering, auto-refresh. Servas via `/dashboard`. |
| **menu.json** | Meny (pizzor, kebabs, burgare, tillbehör, drycker) med id, namn, pris, beskrivning. |
| **orders.json** | Sparade beställningar (persistent). |
| **system_prompt.md** | AI-personlighet för Vapi – svenska, beställningsflöde, när verktyget `place_order` ska anropas. Kopieras till Vapi Assistant. |
| **.env** | API-nycklar: `VAPI_API_KEY`, `GROQ_API_KEY`, `PUSHOVER_USER_KEY`, `PUSHOVER_API_TOKEN`. Optional: `HOST`, `PORT`. |
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
| **KOMPLETT_GUIDE.md** | Komplett svensk guide: Railway, .env, Vapi, Tool-schema, röst (ElevenLabs/Cartesia), felsökning. |
| **RAILWAY_GUIDE.md** | Steg-för-steg: deploya till Railway, Vapi-URL. |
| **STARTA_SYSTEMET.md** | Starta systemet på svenska. |
| **SNABBSTART.txt** | Kort snabbstart. |
| **NUVARANDE_STATUS.md** | Status (t.ex. väntar på Vapi-nyckel). |
| **PROJECT_SUMMARY.txt** | Sammanfattning av levererat (filstruktur, features, hur man kör). |

---

## Teknisk stack

- **Backend:** Python 3, FastAPI, uvicorn, pydantic, requests, python-dotenv.
- **Voice/LLM:** Vapi.ai (telefon + röst + styrning av samtal), Groq (Llama) som LLM i Vapi.
- **Röst:** ElevenLabs med Jonas (svenska) eller Cartesia för lägre latens; undvik Vapis egna röster för svenska.
- **Notiser:** Pushover (push till mobil).
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

## När du hjälper i en ny chatt

- Använd denna fil som **källa till sanning** för projektets omfattning, filer och flöde.
- Ändra bara filer som nämns här (eller lägg till nya om användaren vill utöka systemet).
- API-nycklar ska **aldrig** committas; de finns i `.env` (och .env är i .gitignore).
- Vid problem med Railway, Vapi eller .env: utgå från att all konfiguration beskrivs i RAILWAY_GUIDE.md, KOMPLETT_GUIDE.md och VAPI_SETUP_GUIDE.md.

Om något verkar saknas eller avvika från denna beskrivning, fråga användaren eller läs den aktuella filen i repot.
