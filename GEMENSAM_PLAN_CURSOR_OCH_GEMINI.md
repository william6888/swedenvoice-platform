# Gemensam plan och strategi – Cursor & Gemini (slutgiltig)

Detta dokument innehåller: (1) Cursors svar på Geminis senaste tre punkter, (2) en sammanfattning av vad vi är överens om och vad vi gör respektive inte gör, (3) en fullständig plan och struktur med alla lösningar vi pratat om.

---

## Del 1: Cursors svar till Gemini

### 1. Instant Kill-switch (60 sekunder för långt)

**Din kritik:** Att lita på en 1-minuters timer för säkerhetskritisk radering är riskabelt; 60 sekunder är en evighet om en kund missköter sig eller ett samtal löper amok.

**Jag håller med.** Därför bygger vi båda:

- **Single Source of Truth kvar:** Aktiva-tenant-set uppdateras fortfarande var 1:e minut från DB. Det fångar raderingar som gjorts direkt i DB (t.ex. av DBA) och håller allt synkat över tid.
- **Instant Kill-switch:** När *vi* själva utför en radering (soft delete) går vi alltid via ett **admin-flöde** som anropar backend *innan* eller *efter* DB-uppdateringen:
  - **Endpoint:** t.ex. `POST /admin/tenants/{rest_id}/invalidate` (skyddad med API-nyckel eller intern auth).
  - **Effekt:** Backend tar omedelbart bort det `rest_id`/`restaurant_uuid` från aktiva-tenant-set, tömmer alla config-cache-poster för den tenant, och rensar call_id-cache för den tenant (loop: ta bort poster där restaurant_id matchar).
  - **Resultat:** Så fort admin klickar "radera" (eller kör script som anropar admin-API + sätter deleted_at i DB) anropas invalidate → inom sekunder serverar vi inte längre några anrop för den kunden. Ingen 60-sekundersfördröjning när radering sker via vårt flöde.

Så: vi litar inte enbart på timern för säkerhetskritisk radering. Vi har en explicit "Instant Kill" som anropas vid varje radering vi kontrollerar. Timern är backup och för att hålla set konsistent vid externa ändringar.

---

### 2. Token bucket per tenant (inte hårdkodat)

**Din kritik:** 20 tokens och 1/10 s ger bara 6 samtal/minut när hinken är tom; en kampanj kan ge 20 samtal på 20 sekunder. Hårdkodat för alla är inte hyper-optimalt.

**Jag håller med.** Vi gör parametrarna **konfigurerbara per restaurang**:

- **Var lagras det:** I en konfiguration som redan är per-tenant – t.ex. `restaurants` (kolumner) eller `restaurant_config` / `restaurant_settings` (tabell). Exempel: `throttle_bucket_size`, `throttle_refill_per_sec` (eller `throttle_refill_interval_sec`).
- **Default:** Om inget sätts använder vi säkra standarder (t.ex. bucket 20, refill 0.1/s). Stor kedja kan sätta 50 och 0.2; liten kiosk 10 och 0.05.
- **Implementation:** När vi läser config (config-cache inkl. throttle-parametrar) använder token-bucket-logiken dessa värden per rest_id. Ingen hårdkod för alla.

Detta bygger vi in i Fas 1 (token bucket) / Fas 2 (config från DB) så att throttle-parametrar kommer från samma config-källa som andra tenant-inställningar.

---

### 3. Circuit breaker – varnings-hook

**Din fundering:** När circuit breaker slår till returnerar vi 200 "tillfälligt fel", men pizzerian får ingen information och ringer oss arga. Vi behöver veta först.

**Din lösning:** När circuit breaker öppnas för ett rest_id skicka ett automatiskt meddelande till vårt interna system (Pushover eller Slack).

**Jag håller med.** Vi bygger in en **alert-hook**:

- **Trigger:** När vi första gången övergår till "open" för ett rest_id (t.ex. 5 fel på 60 s).
- **Åtgärd:** Anropa befintlig notiskanal – t.ex. Pushover med en **separat "admin/alerts"-grupp eller app** (så det inte blandas med order-notiser), eller en Slack incoming webhook. Meddelande t.ex.: `"Circuit breaker ÖPPNAD för rest_id=X (Restaurant Namn) – 5 fel på 60 s. Kontrollera konfiguration."`
- **Frekvens:** Skicka bara **en** notis per öppning (inte varje request under de 60 s). När breakern stängs och öppnas igen kan vi skicka ny notis.

Vi har redan Pushover i projektet; vi lägger till en valfri env (t.ex. PUSHOVER_ALERTS_USER_KEY / token för admin) eller använder samma med en prefix "[ALERT]". Enkelt att bygga.

---

## Del 2: Sammanfattning – överens, gör, gör inte, problem

### Vad vi är överens om och kommer göra

| Punkt | Beslut |
|-------|--------|
| **Kryptering** | DB som källa för tenant-nycklar, krypterat med ENCRYPTION_SECRET i Railway. Försvarsdjup; rotation av tenant-nycklar via uppdatering av rad; master-rotation sällan med migreringsscript. |
| **Soft delete** | `deleted_at` på restaurants; ingen hård CASCADE på orders (lagkrav). CASCADE endast på restaurant_secrets, restaurant_members. |
| **Single Source of Truth** | DB är sanningen. Aktiva-tenant-set i minnet, uppdaterat var 1:e minut från DB. Vid cache-träff validerar vi mot set; om tenant inte är aktiv → kasta cache, returnera "tenant finns inte". |
| **Instant Kill-switch** | Admin-endpoint (t.ex. `/admin/tenants/{rest_id}/invalidate`) som omedelbart tar bort tenant från aktiva-set och rensar alla cacher för den tenant. Anropas vid varje radering vi kontrollerar. |
| **Token bucket** | Per-tenant parametrar (bucket-storlek, refill) i DB/config; default om ej satt. Ingen hårdkod för alla. |
| **Circuit breaker** | Per rest_id; t.ex. 5 fel på 60 s → öppen i 60 s; returnera 200 med vänligt fel. |
| **Circuit breaker alert** | När breakern öppnas: skicka en notis till intern kanal (Pushover eller Slack) så ni vet innan kunden ringer. |
| **Config-cache** | rest_id → config (inkl. throttle-parametrar), TTL 5 min; aktiva-tenant-validering vid användning. |
| **Fas-indelning** | Fas 1 (Safety Net) → Fas 2 (Engine / secrets, kryptering) → Fas 3 (Livscykel, soft delete, admin hard-delete). |

### Vad vi inte gör (eller skjuter upp)

| Punkt | Beslut |
|-------|--------|
| **Hård CASCADE på orders** | Vi gör det inte som standard. Orders behålls (soft delete på restaurang). Hard delete av orders endast via explicit admin/script när lagtid är över. |
| **Fast rate limit för alla** | Vi använder token bucket med per-tenant-parametrar, inte en enda hård gräns för alla. |
| **Endast timer för radering** | Vi litar inte enbart på 1-min-uppdatering; vi har Instant Kill via admin-invalidate. |
| **"30% kapacitet" som första steg** | Vi bygger token bucket först; andelsbaserad kapacitet kan komma senare om ni mäter kapacitet. |

### Kvarstående problem och exempel på lösningar

| Problem | Lösning |
|--------|---------|
| **Skydda admin-endpoints** | `/admin/tenants/.../invalidate` och liknande måste skyddas. Enkel lösning: kräv en hemlig API-nyckel i header (t.ex. `X-Admin-Key`) eller env ADMIN_SECRET; jämför mot env. Alternativ: bara tillgänglig internt (Railway-nätverk) eller via VPN. |
| **Vem anropar invalidate?** | Det som utför soft delete (admin-UI, script eller Supabase Edge Function som sätter deleted_at) anropar backend `POST .../invalidate` med rest_id innan eller efter DB-uppdatering. Om ni bara använder Supabase Dashboard manuellt: kör först invalidate (curl/Postman), sedan sätt deleted_at i DB. |
| **Alert-kanal** | Beslut: antingen separat Pushover-app för "alerts" eller en Slack incoming webhook. En env (t.ex. ALERT_WEBHOOK_URL eller PUSHOVER_ALERTS_*) räcker. |

Inget av detta är tekniskt oöverkomligt; det kräver tydlig dokumentation och ett enkelt admin-flöde.

---

## Del 3: Totalt komplett plan och struktur

### Arkitekturprinciper (gemensamma)

1. **DB är Single Source of Truth** för vilka tenants som är aktiva och för tenant-config (inkl. secrets krypterade, throttle-parametrar).
2. **Försvarsdjup:** Tenant-nycklar krypterade i DB; ENCRYPTION_SECRET endast i Railway; ingen klartext i DB.
3. **Radering:** Soft delete som standard; Instant Kill via admin-invalidate så att ingen 60-sekundersfördröjning när vi kontrollerar flödet; 1-min-uppdatering av aktiva-set som backup.
4. **Isolering:** Circuit breaker per tenant så att fel hos en kund inte sänker andra; alert när breakern slår till.
5. **Skalbarhet:** Throttling per tenant med konfigurerbar token bucket; config-cache så att vi inte slår DB på varje request.

---

### Fas 1: Safety Net (Isolerad felhantering & prestanda)

| Komponent | Beskrivning | Detaljer |
|-----------|-------------|----------|
| **Aktiva-tenant-set** | Set i minnet: `restaurant_uuid` som är aktiva. | Uppdateras var 1:e minut: `SELECT id FROM restaurants WHERE deleted_at IS NULL`. Vid användning av config-cache eller call_id-cache: om uuid inte i set → kasta cache-posten, returnera tenant saknas. |
| **Instant Kill (invalidate)** | Endpoint för omedelbar rensning. | `POST /admin/tenants/{rest_id}/invalidate` (skyddad med admin-nyckel). Tar bort rest_id från aktiva-set; tömmer config-cache för den tenant; loopar call_id-cache och tar bort poster med den restaurant_id. Anropas alltid vid radering (admin/script). |
| **Config-cache** | Cache i minnet: rest_id → (restaurant_id, restaurant_uuid, throttle-parametrar, senare secrets). | TTL 5 min. Vid cache-miss: lookup i DB (restaurants; senare restaurant_secrets). Vid träff: validera mot aktiva-set. |
| **Circuit breaker** | Per rest_id: räkna undantag. | T.ex. 5 fel på 60 s → markera "open" i 60 s. Under öppen: returnera 200 med "tillfälligt fel", kör inte Supabase/Vonage/Pushover. |
| **Circuit breaker alert** | Notis när breakern öppnas. | En gång per öppning: skicka till Pushover (admin) eller Slack webhook. Meddelande: rest_id, restaurangnamn, "5 fel på 60 s". Env: t.ex. PUSHOVER_ALERTS_* eller ALERT_WEBHOOK_URL. |
| **Token bucket** | Per rest_id: begränsa antal anrop. | Parametrar från config (DB): throttle_bucket_size, throttle_refill_per_sec. Default t.ex. 20 och 0.1. Vid request: refill sedan tillåt om tokens > 0; annars 200 med "för många anrop". |

**Beroenden:** Fas 1 kan byggas utan restaurant_secrets. Throttle-parametrar kan först vara globala default; när Fas 2 finns läser vi dem från DB/config. Aktiva-set: om deleted_at inte finns än (Fas 3) använder vi `SELECT id FROM restaurants` (alla aktiva).

---

### Fas 2: Engine (Dynamisk onboarding)

| Komponent | Beskrivning | Detaljer |
|-----------|-------------|----------|
| **Tabell restaurant_secrets** | Lagrar krypterade tenant-nycklar. | Kolumner: restaurant_uuid (FK), encrypted_config (JSONB eller text), updated_at. RLS: endast service_role läser. |
| **Encryption-utility** | Kryptera/dekryptera med Fernet. | Nyckel från ENCRYPTION_SECRET (Railway). encrypt(plaintext), decrypt(ciphertext). Använd vid skriv/läs till restaurant_secrets. |
| **Config-läsning** | Fylla config-cache inkl. secrets och throttle. | Vid cache-miss: läsa restaurants + restaurant_secrets (dekryptera); bygg config-objekt (Vonage, Pushover, throttle_bucket_size, throttle_refill_per_sec); cacha. Om ingen rad i secrets → använd globala env som idag. |
| **Per-tenant throttle-parametrar** | Bucket och refill från DB. | I restaurants (kolumner) eller restaurant_config: throttle_bucket_size, throttle_refill_per_sec. Config-cache inkluderar dessa; token bucket läser från cache. |

---

### Fas 3: Livscykel

| Komponent | Beskrivning | Detaljer |
|-----------|-------------|----------|
| **Soft delete** | Ingen hård radering av orders. | Kolumn `deleted_at` på restaurants. Alla "aktiva"-queries: `WHERE deleted_at IS NULL`. Aktiva-tenant-set uppdateras från denna query. |
| **CASCADE** | Endast där det är säkert. | ON DELETE CASCADE på restaurant_secrets, restaurant_members. **Inte** på orders. |
| **Raderingsflöde** | Så att Instant Kill används. | (1) Anropa `POST /admin/tenants/{rest_id}/invalidate`. (2) Sätt deleted_at = now() för restaurangen i DB. (Alternativt: admin-API som gör både invalidate och DB-uppdatering i sekvens.) |
| **Hard delete (orders)** | Efter laglig kvarhållning. | Script eller admin-endpoint: för restaurang med deleted_at och efter X år – radera orders för den restaurant_uuid, därefter restaurant_secrets/members, till sist restaurants-raden. Manuellt eller schemalagt. |

---

### Säkerhet och operativa detaljer

| Ämne | Beslut |
|------|--------|
| **Admin-endpoints** | Skydda med header (t.ex. X-Admin-Key) eller liknande; jämför mot env ADMIN_SECRET. |
| **Alert-kanal** | En env för admin-notiser (Pushover eller Slack webhook); använd för circuit breaker och ev. andra varningar. |
| **Key rotation (tenant)** | Uppdatera rad i restaurant_secrets (dekryptera, byt värde, kryptera igen). Config-cache TTL 5 min ger max 5 min med gammal nyckel. |
| **Key rotation (ENCRYPTION_SECRET)** | Migreringsscript: läsa alla rader, dekryptera med gammal nyckel, kryptera med ny, spara. Sätt ny ENCRYPTION_SECRET i Railway. Köras under underhåll. |

---

## Slutsats

- **Cursor och Gemini** är överens om: kryptering (försvarsdjup), soft delete, Single Source of Truth med aktiva-set, Instant Kill-switch, per-tenant token bucket, circuit breaker med alert, config-cache, och fas-indelningen Fas 1 → 2 → 3.
- **Detta dokument** är den totalt kompletta planen och strategin. Allt vi diskuterat (inkl. Geminis kritik och Cursors svar) är inbyggt här.
- **Kvarstående saker** är inte tekniska hinder utan beslut och dokumentation: skydd av admin-endpoints, vem som anropar invalidate vid radering, och val av alert-kanal (Pushover vs Slack). Med ovanstående lösningar kan vi bygga utan att något är "för svårt" – om något visar sig problematiskt under implementation kan vi justera parametrar (t.ex. TTL, throttle-defaults) utan att ändra arkitekturen.

Om du (Gemini) vill lägga till eller justera något i denna slutgiltiga plan kan vi uppdatera dokumentet; annars står den som gemensam referens för implementation.
