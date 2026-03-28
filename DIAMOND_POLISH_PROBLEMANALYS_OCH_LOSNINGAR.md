# Diamond Polish – Genomgående problemanalys och exemplariska lösningar

**Till dig som chef:** Detta dokument listar **alla** problem (nuvarande, framtida, fler pizzerior, negativ påverkan), **exakt vad som förändras**, och **smartare lösningar** som en erfaren utvecklare skulle välja. Ingenting är implementerat förrän du godkänner.

---

## Del 1: Exakt vad som förändras

### Beteendeändringar (synliga)

| Var | Idag | Efter |
|-----|------|--------|
| **Webhook (POST /vapi/webhook)** | Efter att order sparats och Pushover skickats anropas `send_sms_order_confirmation` i samma request. Vapi får 200 när allt (inkl. SMS) är klart. | Order och Pushover som idag. SMS läggs som BackgroundTask. Vapi får 200 direkt efter sparande + Pushover. SMS skickas strax efter (samma process). Vid SMS-fel: du får en Pushover-alert (PUSHOVER_ALERTS_*) med order_id och fel. |
| **Place_order (POST /place_order, Vapi-format)** | Samma som webhook: SMS anropas synkront, sedan returneras results. | Samma ändring som webhook: SMS i BackgroundTask, 200 direkt, alert vid fel. |
| **Place_order (direct format)** | Skickar inte SMS idag (bara order + Pushover). | Oförändrat. Ingen SMS, ingen BackgroundTask här. |
| **GET /menu** | Anropar `load_menu()` som läser `menu.json` vid varje anrop. | Kan (valfritt) använda meny-cache med TTL 3 min – samma innehåll, färre filläsningar. |
| **find_menu_item()** | Anropar `load_menu()` varje gång. | Kan använda samma cache – ingen beteendeändring, bara snabbare. |
| **Ny endpoint GET /api/keywords** | Finns inte. | Returnerar lista unika produktnamn (och ev. keyterms) från menyn för användning i Vapi (keyword-boosting). |

### Nya beroenden och tillstånd

- **BackgroundTasks:** FastAPI:s inbyggda; ingen ny paketinstallation.
- **Meny-cache:** In-memory dict med TTL 3 min (nyckel t.ex. `menu` eller `menu:{rest_id}`). Ingen ny process eller databas.
- **Alert vid SMS-fel:** Använder befintlig PUSHOVER_ALERTS_* (eller fallback till vanlig Pushover).
- **Payload-logging:** Endast `print` (eller strukturerad logg) vid tool-calls; ingen ny fil eller DB.

### Vad som INTE ändras

- Order-sparande (orders.json + Supabase), Pushover för köket, circuit breaker, token bucket, invalidate, soft-delete, rest_id-flöde, Vapi-svarformat (results med success/order_id). Alla dessa är oförändrade.

---

## Del 2: Alla problem – kategoriserade

### A. Direkta / nuvarande problem

| # | Problem | Beskrivning | Påverkan |
|---|--------|-------------|----------|
| A1 | **Två kodvägar skickar SMS** | Både webhook och `/place_order` (Vapi-format) anropar SMS. Om vi bara flyttar till BackgroundTask i webhook men glömmer `/place_order` blir beteendet inkonsekvent (en väg snabb, andra långsam) och lätt att missa alert på en väg. | Risk för bugg och inkonsekvens. |
| A2 | **Alert vid fel – var skickas den?** | Om PUSHOVER_ALERTS_* inte är satt får du ingen notis vid SMS-fel. Idag används det för circuit breaker. Om det saknas loggas bara. | Du får ingen varning om du inte kollar loggar. |
| A3 | **Vad skickas till BackgroundTask?** | Om vi skickar `Order`-objektet som referens och något ändrar det innan tasken kör (osannolikt men möjligt vid fel i kod) kan tasken få fel data. Om vi skickar `order.model_dump()` och bygger en minimal representation i tasken är det säkrare och oberoende av request-scope. | Stabilitet och förutsägbarhet. |

### B. Framtida problem (när belastning eller antal tenants ökar)

| # | Problem | Beskrivning | Påverkan |
|---|--------|-------------|----------|
| B1 | **Event loop blockad** | BackgroundTask körs i samma process efter svar. `send_sms_order_confirmation` använder `requests.post` (blocking). Under hög samtidighet (många beställningar samtidigt) körs flera tasks efter varandra; under den tiden hanteras inga nya requests på den workern. | Vid många pizzerior och toppar kan svarstiden öka för andra anrop. |
| B2 | **Alert-flood** | Om Vonage är nere eller fel konfiguration ger varje misslyckad SMS en alert. 50 beställningar på 10 min = 50 notiser. | Du blir överöst med varningar och tappar förtroende för kanalen. |
| B3 | **Process kraschar efter 200** | Om processen dör *direkt* efter att vi skickat 200 men *innan* BackgroundTask hunnit köras skickas varken SMS eller alert. | Kund får ingen bekräftelse; du får ingen notis. Kan inte lösas endast med BackgroundTasks. |

### C. Fler pizzerior (multi-tenant)

| # | Problem | Beskrivning | Påverkan |
|---|--------|-------------|----------|
| C1 | **Meny per restaurang** | Idag finns en global `menu.json`. När du lägger till fler pizzerior vill du troligen olika menyer per restaurang. Om vi bygger meny-cache med en global nyckel ("menu") måste vi refaktorera senare. | Framtida tekniska skuld och risk för buggar vid utrullning. |
| C2 | **GET /api/keywords och rest_id** | Om keywords ska vara per restaurang måste endpointen ta `rest_id` och cachen nycklas på `rest_id`. Idag har vi bara en meny – men API:et bör från dag ett acceptera `rest_id` (t.ex. query) så att nya pizzerior bara behöver egen meny (fil eller DB) utan API-ändring. | Negativ påverkan om vi inte tänker från början. |
| C3 | **Alert innehåller rest_id** | Vid SMS-fel måste alerten innehålla vilken restaurang det gäller (rest_id eller namn) så att du vet vilken pizzeria som påverkas. | Annars otydligt vid flera tenants. |

### D. Meny-cache och keywords (Fas 2)

| # | Problem | Beskrivning | Påverkan |
|---|--------|-------------|----------|
| D1 | **Föråldrad meny (stale)** | TTL 3 min betyder att om du uppdaterar menu.json kan det ta upp till 3 min innan nya keywords används (eller GET /menu returnerar ny meny om vi kopplar GET /menu till cache). | Pizzerian uppdaterar meny men AI använder gamla namn i 3 min. |
| D2 | **Keyword-format för Deepgram/Vapi** | Deepgram: "keywords" = enkla ord (inga mellanslag), "keyterms" = fraser. Pizzor med flera ord (t.ex. "Quattro Stagioni", "Kebab med bröd") bör gå som keyterms eller delas. Fel format = ingen förbättring. | Transkriberingen förbättras inte om formatet är fel. |
| D3 | **Känsliga tecken och längd** | Produktnamn med specialtecken eller mycket långa namn kan behöva rensas/trunkeras för att inte avvisas av API. | Potentiella fel eller ignorerade keywords. |
| D4 | **GET /api/keywords – öppen** | Endpointen är publik (inga krav på API-nyckel). Någon som känner till URL:en kan hämta listan. Det är "bara" produktnamn, men konkurrenter kan se er meny. | Mindre problem; kan skyddas senare om ni vill. |

### E. Payload-logging

| # | Problem | Beskrivning | Påverkan |
|---|--------|-------------|----------|
| E1 | **Loggvolym** | Om vi loggar hela `message` vid varje tool-calls kan det bli stort (transkript, ev. audio-referenser). Många beställningar = mycket utskrift. | Svårt att läsa loggar; risk för diskfyllning vid hög trafik. |
| E2 | **Känslig data** | Transkript kan innehålla personuppgifter eller känslig information. Loggar ska inte spara mer än nödvändigt och bör trunkeras. | Sekretess och GDPR-vänlighet. |

### F. Negativ påverkan (saker som kan bli sämre)

| # | Problem | Beskrivning | Påverkan |
|---|--------|-------------|----------|
| F1 | **SMS garanteras inte** | Idag: om request når fram och order sparas, körs SMS i samma request – antingen lyckas det eller så loggas fel. Efter: vi skickar 200 innan SMS körts. Om processen kraschar eller tasken misslyckas kan kunden inte få SMS trots att ordern finns. | Kundupplevelse kan bli sämre i kanten (kund tror order är bekräftad men får ingen SMS). |
| F2 | **Flera workers** | Om Railway kör flera workers har varje worker sin egen meny-cache och sina egna BackgroundTasks. Det är konsekvent men cache är inte delad – varje worker läser fil och cachar själv. Ingen negativ påverkan, bara att TTL gäller per worker. | Ingen direkt negativ effekt. |

---

## Del 3: Exemplariska lösningar (som en riktig expert)

### A1 – En enda plats för "schedule SMS + alert vid fel"

**Lösning:** Inför en **gemensam funktion** som både webhook och `/place_order` anropar:

- `schedule_sms_with_alert_on_failure(background_tasks, order, customer_phone, rest_id)`.
- Inuti: `background_tasks.add_task(_run_sms_and_alert_on_failure, order.model_dump(), customer_phone, rest_id)`.
- `_run_sms_and_alert_on_failure(order_dict, customer_phone, rest_id)`: bygg ett minimalt order-objekt (t.ex. bara det som behövs för SMS-text), anropa `send_sms_order_confirmation`. Vid `False` eller exception: anropa en **gemensam** alert-funktion med order_id, rest_id, felmeddelande.

**Resultat:** Bara en implementation; båda kodvägarna använder samma logik. Ingen duplicering, ingen glömska.

---

### A2 – Alert kanal säker

**Lösning:**

- Om `PUSHOVER_ALERTS_USER_KEY` och `PUSHOVER_ALERTS_TOKEN` är satta: skicka SMS-fel-alert dit.
- Om **inte** satta: **fallback** till vanlig `PUSHOVER_USER_KEY` / `PUSHOVER_API_TOKEN` så att du ändå får en notis (t.ex. med prefix "[ALERT] SMS-fel …"). Dokumentera i `.env.template`: "För SMS-fel-alerts använd PUSHOVER_ALERTS_* om du vill separata kanal; annars används vanlig Pushover."

**Resultat:** Du får alltid notis vid SMS-fel om någon Pushover är konfigurerad.

---

### A3 – Säkra argument till BackgroundTask

**Lösning:** Skicka **aldrig** request-scope-objekt som kan ändras. Skicka `order.model_dump()` (dict), `customer_phone` (str), `rest_id` (str). I tasken: bygg från dict en minimal struktur för `_format_order_sms` (t.ex. Order-modell eller en enkel dataklass med order_id, items-text) och anropa `send_sms_order_confirmation`. Ingen referens till det ursprungliga requesten.

**Resultat:** Ingen risk för att tasken får fel data om något annat skulle mutera objekt.

---

### B1 – Event loop (framtida)

**Lösning:** Ingen kodändring nu. **Dokumentera** i README eller kommentar: "SMS skickas i bakgrunden i samma process. Vid mycket hög samtidighet kan du överväga att flytta SMS till en kö (t.ex. Redis/Celery) eller fler workers." När/när ni ser latens kan ni åtgärda.

**Resultat:** Ingen överkomplexitet idag; tydlig väg framåt.

---

### B2 – Alert-flood

**Lösning:** **Rate-limit för SMS-fel-alert** (enkel, i minnet):

- Håll en struktur: `_SMS_ALERT_LAST_SENT: Dict[str, float]` (nyckel = rest_id, värde = timestamp).
- Innan vi skickar alert: om senaste alert för denna rest_id var inom t.ex. **5 minuter**, skicka **inte** igen (men logga "SMS failed again for rest_id=X, alert suppressed (rate limit)").
- Efter 5 min: skicka igen vid nästa fel.

**Resultat:** Vid Vonage-nedtid får du max en alert per restaurang per 5 min, inte 50. Du ser fortfarande att något är fel.

---

### B3 – Process kraschar efter 200

**Lösning:** Acceptera som känd begränsning. **Dokumentera:** "Om processen startas om direkt efter att vi svarat 200 kan SMS ibland inte skickas; då skickas ingen alert heller. Övervaka processomstarter." Valfritt framtid: persistera "pending_sms" (order_id, telefon, rest_id) i DB och en cron/jobb som retryar – **inte** i denna omgång.

**Resultat:** Tydligt vad som gäller; ingen falsk trygghet.

---

### C1 + C2 – Redo för fler pizzerior från dag ett

**Lösning:**

- **Cache-nyckel:** Alltid `f"menu:{rest_id}"`. Idag: `rest_id` kan defaulta till `"Gislegrillen_01"` (eller `"default"`) eftersom vi bara har en meny-fil. När ni får fler pizzerior: meny per rest_id kan hämtas från fil `menu_{rest_id}.json` eller från DB; då ändrar vi bara var vi **läser** menyn, inte cache-nyckeln.
- **GET /api/keywords:** Tar query-parameter `rest_id` (default `Gislegrillen_01`). Returnerar keywords för den rest_id. Idag: en meny → samma keywords för alla; senare: olika meny per rest_id.

**Resultat:** Noll negativ påverkan när du lägger till pizzerior; bara att fylla på meny per rest_id.

---

### C3 – Alert innehåller rest_id

**Lösning:** I alert-meddelandet alltid inkludera: `order_id`, `rest_id`, och felmeddelande. T.ex. "[ALERT] SMS misslyckades – order_id ORD-…, rest_id Gislegrillen_01, fel: …". Vid flera pizzerior ser du direkt vilken som drabbats.

**Resultat:** Tydligt för dig som chef.

---

### D1 – Stale meny

**Lösning:**

- TTL 3 min är avvägning mellan prestanda och färskhet. **Dokumentera:** "Efter ändring av menu.json: vänta 3 min eller starta om servern för att nya keywords/meny ska gälla."
- **Valfritt men exemplariskt:** Exponera en enkel **admin-rensning** för meny-cache: t.ex. `POST /admin/tenants/{rest_id}/invalidate-menu` (skyddad med X-Admin-Key) som rensar `menu:{rest_id}` i cachen. Då kan du (eller ett framtida admin-gränssnitt) rensa cachen direkt efter menyändring utan omstart.

**Resultat:** Förutsägbart beteende och möjlighet att rensa cache vid behov.

---

### D2 + D3 – Keyword/keyterm-format och säkra namn

**Lösning:**

- Från varje produktnamn:
  - **En ord:** lägg i `keywords` (Deepgram single-word).
  - **Flera ord:** lägg hela namnet i `keyterms` (fraser), och lägg varje ord även i `keywords` om ni vill öka träff (t.ex. "Kebab med bröd" → keyterm + keywords "Kebab", "med", "bröd").
- Sanitering: strip, hoppa över tomma, ta bort tecken som inte är tillåtna (t.ex. endast bokstaver, siffror, mellanslag för keyterms). Truncera varje keyword/keyterm till t.ex. 50 tecken.
- API-svar: `{"keywords": ["…"], "keyterms": ["…"]}`. README: "Klistra in keywords/keyterms i Vapis transcriber-konfiguration enligt deras dokumentation."

**Resultat:** Korrekt format för Vapi/Deepgram och robust mot konstiga namn.

---

### D4 – GET /api/keywords öppen

**Lösning:** Låt den vara öppen idag. **Dokumentera:** "Endpointen är publik. Vid behov kan du skydda den med API-nyckel eller bara anropa den från Vapi (server-side)." Ingen kodändring nu.

**Resultat:** Enkelt; kan stramas åt senare.

---

### E1 + E2 – Payload-logging utan overflow och med respekt för integritet

**Lösning:**

- Logga **inte** hela body. Logga bara vid `event_type == "tool-calls"`.
- Bygg en **säker representation**: t.ex. lista över **nycklar** i `message` + för nycklar som kan innehålla transcript/confidence en **trunkerad** version (max 300 tecken per fält, ingen base64). T.ex. `{k: (v[:300] if isinstance(v, str) else str(v)[:300]) for k, v in message.items()}` och sedan totalt max 1200 tecken för hela loggraden.
- Skriv inte loggen till fil som standard; behåll `print` (stdout) så att ni styrs av Railway/loggaggregator. Om ni senare vill spara för analys kan ni lägga till strukturerad logg till fil med rotation.

**Resultat:** Vi ser om confidence/transcript finns utan att översvämma loggar eller spara känslig data i klartext.

---

### F1 – SMS garanteras inte

**Lösning:** Acceptera som avvägning: **snabbt svar till Vapi** vs **garanti att SMS alltid skickas**. Vi prioriterar snabbt svar. **Dokumentera** för dig: "SMS skickas i bakgrunden. Vid processkrash efter svar kan SMS utebli; kunden kan då ringa tillbaka. Pizzerian har fått ordern via Pushover." Alert vid fel gör att du snabbt ser om Vonage/config är fel.

**Resultat:** Tydlig förväntan; ingen falsk garanti.

---

## Del 4: Sammanfattning – vad som görs och vad som inte görs

| Område | Beslut |
|--------|--------|
| **BackgroundTask** | Webhook + `/place_order` (Vapi-format) använder gemensam `schedule_sms_with_alert_on_failure`; tasken tar dict + telefon + rest_id. |
| **Alert** | Fallback till vanlig Pushover om PUSHOVER_ALERTS_* saknas. Rate-limit: max 1 alert per rest_id per 5 min vid SMS-fel. |
| **Meny-cache** | Nyckel `menu:{rest_id}`, TTL 3 min. Idag en meny (rest_id default); senare enkel att koppla fler menyer. |
| **GET /api/keywords** | Query `rest_id`, returnerar keywords + keyterms, saniterade och format enligt Deepgram. README med exakt URL att klistra in i Vapi. |
| **Payload-logging** | Endast vid tool-calls; trunkerad, säker representation (inga stora eller känsliga fält i klartext). |
| **Direct place_order** | Skickar fortfarande inte SMS; ingen ändring. |
| **Admin invalidate-menu** | Valfritt men rekommenderat: enkel endpoint så du kan rensa meny-cache utan omstart. |

---

## Nästa steg

När du godkänner denna analys och lösningsplan kan implementationen ske enligt Fas 1 (BackgroundTask + alert + payload-logging) och Fas 2 (cache + GET /api/keywords + README) med ovanstående säkerhets- och designval. Om du vill ta bort eller lägga till något (t.ex. hoppa över rate-limit eller alltid kräva PUSHOVER_ALERTS) säg bara till så justerar vi planen innan kod skrivs.
