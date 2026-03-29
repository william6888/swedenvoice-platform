# Onboarding: Ny pizzeria – alla verktyg, steg för steg

Denna fil beskriver **allt** du behöver för att antingen **sätt upp systemet från noll** eller **lägga till en ny pizzeria** i befintlig kedja. Alla verktyg (Vonage, Vapi, Lovable, Supabase, Cursor, GitHub, Railway m.fl.) finns med – enkelt, tydligt och korrekt.

---

## Alla verktyg – översikt

| Verktyg | Var du loggar in / URL | Vad det används till |
|--------|-------------------------|----------------------|
| **GitHub** | github.com → ditt repo | Kod och menyfiler. Ny pizzeria = ny `menu_<rest_id>.json` i repot, push så Railway bygger. |
| **Cursor** | Cursor IDE (lokal) | Redigera kod och menyfiler. Skapa `menu_<rest_id>.json`, ändra i repot. |
| **Railway** | railway.app → ditt projekt | Backend (FastAPI) kör här. En app för alla pizzerior. Variabler (.env) sätts här. |
| **Supabase** | supabase.com → ditt projekt | Databas: tabellerna `restaurants`, `orders`. Ny pizzeria = ny rad i `restaurants`. KDS/Lovable läser härifrån. |
| **Vapi** | vapi.ai/dashboard | Röst-AI. **Ordning i Vapi:** 1) Skapa Assistant, 2) Konfigurera Tools (t.ex. `place_order`), 3) Phone Numbers (Server URL med `?rest_id=...`, koppla Assistant). Ny pizzeria = ny Assistant eller nytt nummer med egen Server URL. |
| **Vonage** | dashboard.nexmo.com | SMS till kund (bekräftelse). Idag global i Railway (.env). Senare kan per-restaurang i `restaurant_secrets`. |
| **Lovable** | lovable.app | Köksdashboard (KDS) som visar ordrar. Läser från Supabase. Ny pizzeria = filtrera på `restaurant_id` / `restaurant_uuid` eller separat vy. |
| **LLM i Vapi** | vapi.ai/dashboard | Välj modell och provider i Assistant (t.ex. en modell som klarar svenska bra). Konfigureras i Vapi, inte i denna backends `.env`. |
| **ElevenLabs** (eller Cartesia) | elevenlabs.io | Röst till Vapi. Kopplas i Vapi Assistant. En röst kan användas för alla pizzerior. |

**Nyckeln som inget blandas ihop:** Varje restaurang har ett **unikt `rest_id`** (t.ex. `Gislegrillen_01`, `PizzeriaSöder_01`). Det används i Supabase (`external_id`), i menyfilen (`menu_<rest_id>.json`), i Vapi webhook-URL (`?rest_id=...`) och i Lovable (filtrera ordrar på `restaurant_id`).

---

## Var man börjar

- **Första gången (sätt upp hela kedjan):** Börja med steg 1 nedan (GitHub + Cursor), sedan Railway → Supabase → Vonage (valfritt) → Vapi → Lovable. En gång klart behöver du bara “Lägg till ny pizzeria” nästa gång.
- **Lägg till pizzeria #2, #3 …:** Börja med “Lägg till ny pizzeria” nedan. Du behöver **inte** skapa nytt Railway-/Supabase-/Vonage-/Lovable-konto – bara ny rad i Supabase, valfri menyfil i repot, och Vapi (ny Assistant eller ny Server URL med `rest_id`).

---

# Del A: Första gången – sätt upp hela kedjan

Följ stegen i ordning. När A är klar har du **en** pizzeria live (t.ex. Gislegrillen). Därefter använder du Del B för varje ny pizzeria.

---

### A1. GitHub + Cursor (kod och meny)

- [ ] **GitHub:** Skapa repo (om du inte har det), pusha projektet (main eller din branch).
- [ ] **Cursor:** Öppna projektmappen. Du ska kunna redigera `menu.json`, `main.py`, och senare skapa `menu_<rest_id>.json`.
- [ ] Bekräfta att `.env` finns lokalt (kopiera från `.env.template`) och att `.env` **inte** committas (finns i `.gitignore`).

---

### A2. Railway (backend)

- [ ] **Railway:** Logga in på [railway.app](https://railway.app) → New Project → **Deploy from GitHub repo** → välj Gislegrillen-repot.
- [ ] **Networking:** Settings → Networking → **Generate Domain**. Notera URL:en (t.ex. `https://gislegrillen-production-xxxx.up.railway.app`). Detta är din **backend-URL** – samma för alla pizzerior.
- [ ] **Variabler:** Projekt → Variables. Lägg till alla från `.env.template` (se tabellen A8). Minst: `VAPI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `ADMIN_SECRET`. Om du ska skicka SMS: `VONAGE_API_KEY`, `VONAGE_API_SECRET`, `VONAGE_FROM_NUMBER`.
- [ ] Efter deploy: öppna `https://<din-railway-url>/health` – ska returnera OK.

---

### A3. Supabase (databas)

- [ ] **Supabase:** Logga in på [supabase.com](https://supabase.com) → skapa projekt (eller använd befintligt).
- [ ] **Tabeller:** Säkerställ att du har tabellerna **`restaurants`** (minst kolumner: `id`, `external_id`, `name`, `deleted_at`; valfritt: `throttle_bucket_size`, `throttle_refill_per_sec`) och **`orders`** (enligt backend: `restaurant_id`, `restaurant_uuid`, `customer_name`, `customer_phone`, `items`, `total_price`, `status`, m.m.).
- [ ] **Första restaurangen:** I **`restaurants`** lägg in en rad för Gislegrillen: `external_id` = `Gislegrillen_01`, `name` = t.ex. "Gislegrillen", `deleted_at` = NULL. Notera **`id`** (UUID) – det är `restaurant_uuid`.
- [ ] **API-uppgifter:** Project Settings → API. Kopiera **Project URL** och **anon public key**. Sätt i Railway Variables som `SUPABASE_URL` och `SUPABASE_KEY`.

---

### A4. Vonage (SMS, valfritt)

- [ ] **Vonage:** Logga in på [dashboard.nexmo.com](https://dashboard.nexmo.com). Skapa app / använd befintlig. Hämta **API Key** och **API Secret**.
- [ ] Skaffa ett **From Number** (virtuellt nummer för att skicka SMS). Format t.ex. `+46701234567`.
- [ ] Sätt i Railway: `VONAGE_API_KEY`, `VONAGE_API_SECRET`, `VONAGE_FROM_NUMBER`.

---

### A5. Kök och ordrar (ingen separat push-app)

- [ ] Köket ser ordrar via **Lovable** (Supabase) och/eller inbyggd **dashboard** (`/dashboard`). Servern skriver även **köksbong** i Railway-loggar. Circuit breaker och SMS-fel loggas som `[ALERT]` i samma loggar.

---

### A6. Vapi (röst-AI + telefon)

**Ordning i Vapi (som i dashboarden): först Assistant → sedan Tools → sedan Phone Numbers.** Gör stegen i den ordningen.

- [ ] **Vapi:** Logga in på [vapi.ai/dashboard](https://vapi.ai/dashboard). Under **API Keys** / **Integrations**: koppla den **LLM-provider** och **röst** (t.ex. ElevenLabs eller Cartesia) du valt för Assistanten.

**Steg 1 – Assistant (BUILD → Assistants)**  
- [ ] Klicka **Create Assistant** (eller skapa ny). Namn t.ex. "Gislegrillen Order Bot" (eller "Riley" / restaurangens namn).
- [ ] **Model:** Välj provider och modell i Vapi som passar svenska (enligt Vapis aktuella utbud). First Message Mode: "Assistant speaks first". **First Message:** t.ex. "Välkommen till Gislegrillen, vad vill du beställa?"
- [ ] **System prompt:** Kopiera **hela** innehållet från `system_prompt.md` (i repot) till Assistant-fältet. (Personlighet, språk, arbetsflöde, när `place_order` ska anropas.)
- [ ] **Voice (fliken Voice):** Välj ElevenLabs, röst Jonas (svenska) eller Cartesia med svensk röst. Språk: Swedish (sv-SE). Spara Assistant.

**Steg 2 – Tools (BUILD → Tools)**  
- [ ] Gå till **Tools** i sidomenyn. Skapa eller redigera tool **`place_order`**.
- [ ] **URL:** `https://<DIN-RAILWAY-URL>/vapi/webhook?rest_id=Gislegrillen_01` (ersätt med din Railway-URL). Method: POST.
- [ ] **Parameters/Schema:** enligt **VAPI_SETUP_GUIDE.md** (items med id, name, quantity; special_requests valfritt). Beskrivning t.ex. "Placera beställning när kunden bekräftat."
- [ ] Spara tool. **Koppla tool till Assistant:** i Assistant (Model eller Tools-flik) – lägg till tool `place_order` så att assistenten kan anropa den.

**Steg 3 – Phone Numbers (BUILD → Phone Numbers)**  
- [ ] Gå till **Phone Numbers**. Klicka **Create Phone Number** (eller köp/koppla nummer via Vonage).
- [ ] **Phone Number Label:** t.ex. "Gislegrillen" (tydligt namn så du ser vilken restaurang det är).
- [ ] **Server URL:** samma som ovan: `https://<DIN-RAILWAY-URL>/vapi/webhook?rest_id=Gislegrillen_01`. Timeout t.ex. 20 s.
- [ ] **Inbound Settings:** **Tilldela denna telefonnummer till din Assistant** (Riley / Gislegrillen Order Bot) så att inkommande samtal hanteras av just den assistenten (med rätt `rest_id` i URL:en).
- [ ] Spara. Då är kedjan klar: samtal → nummer → Assistant → tool `place_order` → din backend.

- [ ] **Testa:** Ring numret, lägg en testbeställning. Kontrollera att ordern sparas i Supabase och att SMS fungerar om Vonage är konfigurerat.

---

### A7. Lovable (köksdashboard KDS)

- [ ] **Lovable:** Logga in på [lovable.app](https://lovable.app). Skapa eller öppna Gislegrillen-KDS-projektet.
- [ ] **Supabase-koppling:** I projektets Settings/Integrations, koppla **samma** Supabase som Railway använder (Project URL + anon key). Lovable ska läsa från tabellen **`orders`**.
- [ ] **Köksvy:** Säkerställ att appen hämtar ordrar från `orders` (t.ex. via edge-funktion som anropar Supabase eller direkt query). För **en** restaurang kan du filtrera på `restaurant_id = 'Gislegrillen_01'`. För flera restauranger: filtrera på `restaurant_id` eller `restaurant_uuid` beroende på inloggad användare / val av restaurang.
- [ ] Verifiera: lägg en testorder via Vapi → ordern ska synas i Lovable (rätt restaurang).

---

### A8. Referens: Variabler som ska finnas i Railway

| Variabel | Obligatorisk | Kommentar |
|----------|---------------|-----------|
| VAPI_API_KEY | Ja | Från vapi.ai |
| SUPABASE_URL | Ja | Supabase Project URL |
| SUPABASE_KEY | Ja | Supabase anon (eller service) key |
| ADMIN_SECRET | Ja | Egen hemlig sträng för /admin/* |
| VONAGE_API_KEY | Valfritt | SMS till kund |
| VONAGE_API_SECRET | Valfritt | |
| VONAGE_FROM_NUMBER | Valfritt | +46... |
| RESTAURANT_UUID | Valfritt | Fallback om Supabase saknas; annars från `restaurants.id` |
| ENCRYPTION_SECRET | Valfritt | För Fas 2 tenant-nycklar (restaurant_secrets) |
| WEBHOOK_SHARED_SECRET | Valfritt | Auth på POST /place_order och /vapi/webhook |

---

# Del B: Lägg till en ny pizzeria (multi-tenant)

När kedjan redan kör (Del A klar) behöver du **inga nya konton**. Du gör bara följande, i ordning.

---

### B1. Välj unikt `rest_id`

- [ ] Välj ett **stabil** ID för den nya restaurangen: t.ex. `PizzeriaSöder_01`, `GatukökNord_01`. Bara bokstäver, siffror, understreck.
- [ ] Kontrollera att det **inte** redan finns i Supabase `restaurants.external_id`. Gislegrillen har `Gislegrillen_01` – använd inte det här.

---

### B2. Supabase

- [ ] Öppna **Supabase** → Table Editor → **`restaurants`**.
- [ ] Insert row: **`external_id`** = ditt valda `rest_id`, **`name`** = visningsnamn, **`deleted_at`** = NULL. Spara. Notera **`id`** (UUID).

---

### B3. Meny (Cursor + GitHub + Railway)

- [ ] **Cursor:** Om den nya pizzerian har **egen meny**: skapa **`menu_<rest_id>.json`** i projektroten (samma struktur som `menu.json`). Om menyn är **samma** som Gislegrillen behöver du ingen ny fil – backend använder då `menu.json`.
- [ ] **GitHub:** Commit och push. **Railway** bygger automatiskt om du har Deploy from GitHub – då blir den nya menyfilen tillgänglig.
- [ ] Efter deploy (eller om du inte ändrat fil): anropa **`POST https://<RAILWAY-URL>/admin/menu/invalidate?rest_id=<rest_id>`** med header **`X-Admin-Key: <ADMIN_SECRET>`** så cachen uppdateras direkt (annars vänta 3 min).

---

### B4. Vapi (samma ordning: Assistant → Tools → Phone Numbers)

**Ordning i Vapi:** 1) Assistant, 2) Tools, 3) Phone Numbers. För ny pizzeria gör du antingen **ny Assistant + nytt Tool-URL + nytt nummer** eller **återanvänder Assistant** men med **nytt nummer som har egen Server URL** med `rest_id`.

- [ ] **1) Assistant:** Skapa **ny Assistant** för denna pizzeria (t.ex. "Pizzeria Söder Bot") med eget First Message och system prompt, **eller** återanvänd befintlig. Om du återanvänder: kom ihåg att `rest_id` måste komma från Phone Number Server URL (steg 3).
- [ ] **2) Tools:** Tool **`place_order`** – antingen skapa **ny kopia** av tool med URL  
  `https://<DIN-RAILWAY-URL>/vapi/webhook?rest_id=<rest_id>`  
  (ersätt `<rest_id>` med t.ex. `PizzeriaSöder_01`), eller se till att assistenten anropar en tool som får `rest_id` från **Server URL på Phone Number** (då sätter du bara URL med `?rest_id=...` på numret i steg 3). Koppla rätt tool till denna Assistant.
- [ ] **3) Phone Numbers:** **Create Phone Number** (eller använd befintligt). **Phone Number Label:** t.ex. "Pizzeria Söder". **Server URL:**  
  `https://<DIN-RAILWAY-URL>/vapi/webhook?rest_id=PizzeriaSöder_01`  
  (samma `rest_id` som i Supabase). **Inbound Settings:** Tilldela **denna** Assistant till detta nummer så att samtal till det numret går till rätt restaurang.
- [ ] Resultat: När någon ringer detta nummer → Vapi skickar till din backend med `rest_id` i URL → rätt meny och rätt restaurang i Supabase.

---

### B5. Vonage (idag)

- [ ] **Idag:** Samma Vonage för alla (Railway Variables) om SMS används. Ingen ändring behövs för ny pizzeria om ni delar samma avsändarnummer.
- [ ] **Senare:** Om du vill ha egna SMS per restaurang använder du tabellen **`restaurant_secrets`** (Fas 2) med krypterad config per `restaurant_uuid`.

---

### B6. Lovable (KDS för den nya restaurangen)

- [ ] **Lovable:** Köksvyn måste kunna visa ordrar för den nya restaurangen. Det gör du genom att:
  - antingen **filtrera** på `restaurant_id` = `<rest_id>` (eller `restaurant_uuid` = den nya radens `id`) när användaren väljer restaurang / loggar in,
  - eller ha **separat vy/länk** per restaurang med rätt filter.
- [ ] Ingen ny Lovable-app behövs – samma app, filtrera på `restaurant_id` / `restaurant_uuid` så att varje kök bara ser sina ordrar.

---

### B7. Testa

- [ ] Ring det telefonnummer som är kopplat till den nya restaurangen.
- [ ] Lägg en testbeställning. Kontrollera:
  - [ ] **Supabase** → `orders`: ny rad med **`restaurant_id`** = `<rest_id>` och **`restaurant_uuid`** = den nya restaurangens UUID.
  - [ ] **Lovable:** Logga in / välj den restaurangen – ordern ska synas i köksvyn.
  - [ ] SMS om Vonage är konfigurerat.
- [ ] Om du skapade `menu_<rest_id>.json`: verifiera att rätt rätter och priser används.

---

## Snabbkontroll: har jag glömt något?

| Kontroll | Ja/Nej |
|----------|--------|
| Unikt `rest_id` som inte används av annan restaurang? | |
| Rad i Supabase `restaurants` med `external_id` = `rest_id`, `deleted_at` = NULL? | |
| Meny: antingen `menu_<rest_id>.json` (pushad till GitHub så Railway har den) eller samma som andra? | |
| Vapi webhook-URL innehåller `?rest_id=<rest_id>` (eller metadata satt)? | |
| Telefonnumret kopplat till rätt Assistant/URL? | |
| Efter menyändring: invalidate anropad eller 3 min väntat? | |
| Lovable visar ordrar för denna restaurang (filter på `restaurant_id`/`restaurant_uuid`)? | |

---

## Sammanfattning – alla verktyg i ordning

**Första gången:** GitHub → Cursor → Railway (deploy + variabler) → Supabase (tabeller + första restaurang + API-nycklar) → Vonage (valfritt) → Vapi (Assistant, webhook med `rest_id`, nummer) → Lovable (koppla Supabase, visa ordrar).

**Ny pizzeria:** Välj `rest_id` → Supabase (ny rad i `restaurants`) → Cursor/GitHub (valfri `menu_<rest_id>.json`, push) → Railway (ingen ändring) → Vapi (ny Assistant eller ny Server URL med `?rest_id=...`, koppla nummer) → Vonage (ingen ändring om delad) → Lovable (filtrera på ny `restaurant_id`/`restaurant_uuid`) → Testa.

Inget blandas ihop om **ett unikt `rest_id`** används överallt: Supabase, menyfil, Vapi-URL och Lovable-filter.
