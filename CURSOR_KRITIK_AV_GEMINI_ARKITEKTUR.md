# Cursor: Kritisk analys av Geminis "Metadata-Driven Multi-Tenancy"-förslag

Jag har gått igenom Geminis text rad för rad, ifrågasatt antaganden och identifierat var det håller, var det sviktar, och vad som behöver till om det ska bli hyper-optimalt och byggbart.

---

## Del 1: Kritik och analys av det Gemini skrivit

### 1. Database-as-Config och `restaurant_secrets`

**Vad Gemini säger:** Flytta API-nycklar från Railway till tabellen `restaurant_secrets`, krypterade. ENCRYPTION_SECRET i Railway för dekryptering. Dynamisk lookup på `rest_id`.

**Kritik och problem:**

- **"110 variabler för 10 kunder"** – I praktiken sätter man inte 110 env-variabler i Railway. Man har globala variabler (SUPABASE_URL, SUPABASE_KEY, etc.) och tenant-specifika *data* i databasen. Så problemformuleringen är lite överdriven. Riktningen (DB som källa för kundspecifika nycklar) är dock rätt.
- **ENCRYPTION_SECRET i Railway** – Du har fortfarande en hemlighet i miljön. Om den läcker kan alla tenant-nycklar dekrypteras. Det du vinner är: nycklar i klartext i DB-backups läcker inte; du behöver inte ha Vonage/Pushover per kund i env. Det är "encryption at rest", inte "inga hemligheter någonstans".
- **Hur kommer nycklarna in?** Om Pizzeria Rix ska ha egen Vonage/Pushover: vem sätter det i `restaurant_secrets`? Supabase Dashboard (manuellt) = nycklar i webbläsaren. Eget admin-API = kräver auth och säker hantering. Rotering av nycklar blir mer komplext än idag.
- **RLS "endast backend kan läsa"** – Backend använder förmodligen `service_role`, som bypassar RLS. Så "extremt strikt RLS" gäller andra roller (t.ex. anon/authenticated). Bra, men det är inte RLS som skyddar mot att backend läcker – det är applogik och att man inte loggar/exponerar secrets.

**Slutsats:** Konceptet fungerar tekniskt, men antagandet att "då behöver vi inte variabler" är fel – du behöver fortfarande globala secrets (Supabase, ev. ENCRYPTION_SECRET). Det viktiga är: per-tenant-nycklar utan ny deploy, och att nycklar inte ligger i klartext i DB. Det kräver tydlig onboarding- och rotationsstrategi.

---

### 2. "The Atomic Eraser" (ON DELETE CASCADE)

**Vad Gemini säger:** ON DELETE CASCADE på alla FKs kopplade till `restaurant_uuid`. När du raderar en rad i `restaurants` raderas ordrar, secrets, members, "cachade sessioner". Cachen i minnet på Railway ska också rensas.

**Kritik och problem:**

- **"Cachade sessioner"** – Vi har ingen session-tabell per tenant. Vi har en *in-memory* `call_id`-cache (call_id → restaurant). Den sitter i backend-minnet. Supabase vet inte när du raderar en restaurang; databasen kan inte anropa Railway. Så "atomic" är bara atomic *i databasen*. För att rensa cachen måste du antingen:
  - ha ett flöde där *du* anropar en backend-endpoint (t.ex. "flush cache för rest_id") efter radering, eller
  - acceptera att cache-poster för den restaurangen dör ut av TTL (t.ex. 1 timme), eller
  - vid cache-träff kolla "finns denna rest_id kvar i DB?" (extra DB-roundtrip på varje anrop).
  Så "rensa cachen vid radering" kräver explicit design (t.ex. admin-API som först raderar i DB, sedan anropar backend för cache-flush).
- **Raderar alla ordrar (CASCADE)** – Juridiskt och bokföringsmässigt kan det vara känsligt. Många länder kräver att orderhistorik bevaras i X år. "Total spårfrihet" kan alltså stå i konflikt med krav på datalagring. Det bör vara ett medvetet val (och ev. dokumenterat), inte bara "cascade överallt".
- **Praktisk CASCADE:** På `restaurant_secrets`, `restaurant_members` och ev. andra tenant-kopplade tabeller är CASCADE rimligt. På `orders` är det ett tydligt "radera allt för den kunden"-val.

**Slutsats:** CASCADE i DB är enkelt att införa och ger ren radikal radering i DB. Men: (1) cache-rensning är *inte* automatisk utan kräver ett flöde som involverar backend, (2) att radera alla ordrar kan vara olämpligt ur lag/ekonomi – värt att ifrågasätta.

---

### 3. Config-cache (5 min)

**Vad Gemini säger:** Slå inte upp API-nycklar i DB vid varje sekund; använd en cache (t.ex. 5 min) i backend.

**Kritik:** Ingen – det är standard och nödvändigt om konfiguration hämtas från DB.

**Notering:** Vid nyckelbyte i DB används gamla nyckeln i upp till 5 min. För de flesta fall acceptabelt; vid kris (nyckel läckt) behöver man kunning ev. cache-purge eller kort TTL.

**Slutsats:** Håller helt. Bör ingå i designen.

---

### 4. Circuit breaker per `rest_id`

**Vad Gemini säger:** Om en kund (t.ex. Pizzeria Rix) har trasig konfiguration som ger upprepade fel, "svartlista" det `rest_id` i 60 sekunder så att andra kunder (Gislegrillen) inte påverkas.

**Kritik och nyans:**

- Vi har redan föreslagit detta (i CURSOR_SVAR_TILL_GEMINI_PLAN, avsnitt 7). Riktningen är rätt.
- **Vad räknas som fel?** Vonage-timeout? Pushover-fel? Supabase-fel? Om *något* fel för det tenant:et triggar breakern blir det enkelt men grovt (hela tenant i "maintenance" i 60 s). Om bara t.ex. Vonage fel räknas blir logiken mer rättvis men mer komplex (per-tjänst breaker). För att börja: "något fel för detta rest_id" → öka räknare; efter t.ex. 5 fel på 1 min → circuit open 60 s. Enkelt och skyddar servern.
- **Var ska räknaren ligga?** I minnet per process. Vid flera Railway-replicas delar de inte state – då gäller breakern per replika. För er skala (en replika) är det OK.

**Slutsats:** Bra och byggbart. Definiera tydligt vad som räknas som "failure" (t.ex. exception i webhook-hanteringen för det anropet).

---

### 5. Global throttling ("max 30% per restaurang")

**Vad Gemini säger:** Ingen enskild restaurang får använda mer än 30% av serverns totala kapacitet.

**Kritik och problem:**

- **"30% av kapacitet"** – Odefinierat. 30% av CPU? Minne? Req/s? Samtidiga anrop? För att implementera behöver du: (a) mätbar "total kapacitet" (t.ex. max N req/s eller M samtidiga anrop), (b) per-tenant-räknare, (c) avvisa nya anrop för en tenant när den når 30%. Det kräver både metriker och state.
- **Praktiskt:** Enklare och nästan lika effektivt: **per-tenant rate limit** (t.ex. max 20 req/min per `rest_id`). Då kan en enda kund inte DoS:a andra; "30%"-gränsen kan komma senare om ni har tydliga kapacitetsmål.
- **Verklig risk idag:** Ni har få kunder; risken är mer "en kund med trasig integration som spam:ar" än "en kund som legitimit använder 50% CPU". Circuit breaker + per-tenant rate limit adresserar det.

**Slutsats:** Idén är god men oklar och tung att implementera exakt som "30% kapacitet". Rekommendation: ersätt med en enkel **per-tenant rate limit** (req/min eller req/s) som första steg; behåll möjlighet att senare lägga till hårdare "andels"-begränsning om ni mäter kapacitet.

---

### 6. Zero-touch onboarding

**Vad Gemini säger:** Ny kund = DB-insert + Vapi-konfiguration, ingen ny deploy eller ändring av Railway-variabler.

**Kritik och nyans:**

- **"Zero-touch"** – Tolkning: zero-touch *för deploy* (ingen ny kod eller env-ändring per kund). Det är uppnåelbart: nya kunder = rad(er) i `restaurants` (+ ev. `restaurant_secrets`) + skapa/duplicera assistent i Vapi med Server URL `...?rest_id=NYTT_ID`.
- **Vem gör insert?** Någon måste sätta in data: du i Supabase Dashboard, ett admin-API, eller ett script. "Zero-touch" betyder inte att ingen människa eller process gör något – det betyder att *samma* backend och samma Railway-deploy hanterar alla kunder.
- **Vapi:** Att skapa en ny assistent (eller kopiera mall) och sätta webhook-URL görs idag manuellt eller via Vapi API. För många kunder: script eller admin-UI som anropar Vapi API. Det är fortfarande zero-touch * från deploy*-perspektiv.

**Slutsats:** Målet är rimligt och nåbart. Kräver tydligt flöde: hur lägger man in restaurang + secrets (och ev. Vapi-assistent) – manuellt, script eller admin-API.

---

## Del 2: Identifierade lösningar, problem och förslag

### A) Config migration och `restaurant_secrets`

| Problem | Lösning / förslag |
|--------|--------------------|
| Alla nycklar i DB kräver säker onboarding | Börja med att endast *överrida* per tenant där det behövs. Globala Vonage/Pushover i Railway som default; `restaurant_secrets` endast för kunder med egna nycklar. |
| ENCRYPTION_SECRET är single point of failure | Acceptera att den finns i Railway; använd den bara för att kryptera i DB. Rotera den sällan och dokumentera proceduren. |
| Latency vid varje anrop | **Config-cache:** `rest_id` → dekrypterad config, TTL t.ex. 5 min. Vid cache-miss: läs från DB, dekryptera, cacha. |

**Struktur för `restaurant_secrets` (förslag):**  
Kolumner t.ex. `restaurant_uuid` (FK till `restaurants`), `key_name` (t.ex. `vonage_api_key`, `pushover_token`), `encrypted_value`, `updated_at`. Alternativt en JSONB-kolumn `encrypted_config` med alla nycklar för den restaurangen. RLS så att endast service_role (backend) kan läsa.

---

### B) Atomic deletion och cache

| Problem | Lösning / förslag |
|--------|--------------------|
| DB CASCADE rensar inte backend-cache | **Orchestration:** Admin- eller intern endpoint, t.ex. `POST /admin/restaurants/{rest_id}/delete`: (1) radera i Supabase (restaurang, så CASCADE tar secrets, members, ev. orders), (2) anropa samma backend för "flush cache för rest_id". I backend: loop över `_CALL_RESTAURANT_CACHE` och ta bort poster där `restaurant_id == rest_id`. |
| Rättslig krav på orderhistorik | Overväg **soft delete**: `restaurants.deleted_at` istället för radering; filtrera bort borttagna överallt. Eller CASCADE bara på `restaurant_secrets` och `restaurant_members`, och hantera orders separat (arkivering eller manuell radering efter X år). |

**Cache-rensning:** Hålla i cache `restaurant_id` (eller `rest_id`) tillsammans med `restaurant_uuid` (det gör vi redan), så vid flush kan vi: `for call_id, entry in list(cache.items()): if entry.get("restaurant_id") == rest_id: del cache[call_id]`.

---

### C) Circuit breaker

| Problem | Lösning / förslag |
|--------|--------------------|
| Vad ska räknas som fel? | Börja enkelt: *något* undantag i webhook-hanteringen för det anropet (redan fångat av request-isolering). Öka felräknare för `rest_id`; efter t.ex. 5 fel inom 60 s → markera tenant som "open" i 60 s; returnera 200 med "tillfälligt fel" utan att köra Supabase/Vonage/Pushover. |
| State vid flera replikas | Acceptera per-replika-state tills ni har flera replikas; då kan ni senare övergå till delad state (t.ex. Redis) om ni behöver. |

---

### D) Throttling

| Problem | Lösning / förslag |
|--------|--------------------|
| "30% kapacitet" är odefinierat och tungt | **Fas 1:** Per-tenant rate limit (t.ex. max 30 req/min per `rest_id`). Enkel in-memory-räknare per rest_id, återställ varje minut. När gräns nådd: returnera 200 med "för många anrop, försök igen om en stund". **Fas 2:** Om ni mäter kapacitet (t.ex. max 100 req/s totalt) kan ni sätta andelsgräns per tenant (t.ex. 30%). |

---

### E) Prioritering (hyper-optimal ordning)

Om ni bygger steg för steg, utan "vilda försök":

1. **Config-cache för nuvarande lookup** – Ni har redan tenant-lookup (rest_id → restaurant_uuid). Om ni senare lägger till `restaurant_secrets`, gör config-cache (rest_id → config, TTL 5 min) *samtidigt* så att ni inte slår upp DB på varje anrop.
2. **Circuit breaker per rest_id** – Enkel in-memory-logik; stora vinster vid trasiga kunder. Kan implementeras utan DB-ändringar.
3. **restaurant_secrets + kryptering** – När ni verkligen har kunder med egna Vonage/Pushover. Designa tabell + RLS + en Python-funktion som hämtar och dekrypterar (med cache).
4. **Atomic deletion-flöde** – Admin-endpoint som raderar i DB och rensar cache; CASCADE där det är lagligt och önskat.
5. **Per-tenant rate limit** – När ni ser behov (många kunder eller risk för missbruk). "30% kapacitet" kan vänta tills ni har tydliga mätvärden.

---

## Sammanfattning

- **Geminis riktning** (DB som config, CASCADE, circuit breaker, cache, zero-touch från deploy) är rätt.
- **Kritik:** 110 variabler är överdrivet; cache-rensning vid radering är inte automatisk utan kräver flöde; "30% kapacitet" är oklart; total radering av orders kan strida mot lag; secrets-onboarding och rotation behöver tänkas igenom.
- **Lösningar:** Config-cache (5 min), circuit breaker (definiera "fel"), per-tenant rate limit istället för 30%-regel till att börja med, orchestrated delete (admin + cache-flush), och val av soft delete vs CASCADE på orders utifrån juridik och policy.

Om du vill kan nästa steg vara en konkret PDS: först "Circuit breaker + config-cache (för nuvarande lookup)", sedan "Design av restaurant_secrets och migrationssteg", och till sist "Delete-flöde och cache-flush".
