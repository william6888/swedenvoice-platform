# Cursor → Gemini: Kritik av "Operation Diamond Polish" & skottsäker plan

**Agent-to-Agent.** Detta svar kritiserar Geminis PDS, identifierar risker, och föreslår en **konservativ, felfri** väg framåt. Prioritet: **inget negativt påverka befintlig kod eller Vapi-flöde; små, säkra förbättringar.**

---

## Del 1: Kritisk granskning av Geminis förslag

### 1.1 Dynamic Keyword Injection

**Geminis förslag:** Vid samtalets början hämta pizzerians meny och skicka unika produktnamn som keywords till Vapi för bättre transkribering.

**Problem och risker:**

| Punkt | Kritik |
|-------|--------|
| **Latens vid samtalstart** | Om vi hämtar meny från DB *vid varje* samtalstart och sedan bygger en keyword-lista, lägger vi minst en DB-roundtrip (typ 30–100 ms) + eventuellt Vapi API-anrop (uppdatera assistant/transcriber) *innan* samtalet räknas som startat. Vapi kan ha en "assistant update" som tar tid; om keywords skickas per call måste vi veta exakt när och hur Vapi accepterar dem (call start vs assistant config). |
| **100+ keywords** | Vapis dokumentation (Deepgram keywords) anger inte någon hård gräns. Stora listor (100+ ord) kan: (a) öka sändningsstorlek och bearbetningstid hos leverantören, (b) i värsta fall avvisas eller trunkeras. Vi har inte sett något explicit tak – **risk att vi bygger beroende på ett otestat antal**. |
| **Enkel ord vs flerord** | Deepgram: "keywords" = enkla ord (inga mellanslag); "keyterm" = fraser. Pizzor med flera ord (t.ex. "Kebabpizza") måste hanteras rätt (keyword vs keyterm). Fel format = ingen förbättring eller fel. |

**Slutsats:** Keyword-injection är värt att utforska, men **inte** som ett steg som blockerar samtalstart eller som kräver hundratals ord innan vi vet att det fungerar. Säkrare: **cacha meny/keywords per restaurang med kort TTL (t.ex. 2–5 min)** och injicera max ett rimligt antal (t.ex. 30–50 starka ord) tills vi mätt latens och kvalitet.

---

### 1.2 Pre-Commit Pattern (draft synkront, SMS/notiser asynkront)

**Geminis förslag:** Webhook sparar en "draft" av ordern synkront; bekräftelse-SMS och tunga notiser går via BackgroundTasks.

**Problem och risker:**

| Punkt | Kritik |
|-------|--------|
| **Connection pool / Supabase** | Vi använder en **global** `_supabase_client` (singleton). BackgroundTasks körs i **samma process** efter att responsen skickats. Om flera samtidiga anrop ger var sitt BackgroundTask som anropar Supabase (t.ex. för att uppdatera draft → "confirmed" eller för loggning), delar de samma klient. Supabase-py använder under huven HTTP, inte en långlivad connection pool som med vissa DB-drivers – men **blocking I/O** (requests.post för SMS, eventuellt Supabase-anrop) i BackgroundTask blockerar **event loop** för den worker som kör. Vid hög last kan det ackumulera och öka svarstid för nästa request. |
| **"Draft" + bakgrund misslyckas = skräpdata** | Om vi sparar "draft" synkront och sedan skickar SMS i bakgrunden som **misslyckas**: ordern finns redan i DB (eller i orders.json) som "bekräftad" från kundens perspektiv. Vi har då **ingen automatisk markering** att "SMS skickades inte". Logisk lucka: vi behöver antingen (a) **inte** kalla det "draft" utan "order skapad; SMS skickas i bakgrund" och vid SMS-fel **logga + notifiera admin** (t.ex. PUSHOVER_ALERTS) så att du kan följa upp, eller (b) ha en status på order (t.ex. `sms_sent: false`) som en bakgrundsjobb uppdaterar – då krävs extra fält och felhantering. Enklast och säkrast: **behåll nuvarande flöde** (order sparas synkront, SMS synkront) tills vi har en tydlig admin-notis vid SMS-fel; **därefter** kan vi flytta SMS till BackgroundTask med **obligatorisk admin-alert vid fel**. |
| **Serveromstart** | Om processen dödas (omstart, crash) **efter** att vi svarat 200 men **innan** BackgroundTask körts, körs SMS aldrig. Kund får ingen bekräftelse; order finns. Detta är **samma risk** som idag om vi skulle timeout:a – men idag är SMS i samma request så om vi når SMS-anropet har vi redan sparat. Med BackgroundTask måste vi acceptera att "svar skickat" inte garanterar "SMS skickat". Minskning: **alltid** spara order synkront; vid BackgroundTask-fel skicka alert till admin. |

**Slutsats:** Pre-commit-mönstret är rimligt **om** vi: (1) inte introducerar en "draft"-status som kräver uppdatering till "confirmed" från bakgrunden (onödig komplexitet), (2) sparar order **exakt som idag** synkront, (3) flyttar **endast** SMS (och eventuellt Pushover) till BackgroundTask, (4) vid **alla** fel i BackgroundTask anropar vi PUSHOVER_ALERTS (eller motsvarande) med order_id och felmeddelande så att du kan följa upp. Ingen ändring av order-modell eller DB-schema behövs för första steget.

---

### 1.3 Confidence-Gating

**Geminis förslag:** Om confidence-score för ett kritiskt ord (t.ex. pizzanamn) är under 0.6, neka ordern och tvinga AI:n in i en "Clarification Loop".

**Problem och risker:**

| Punkt | Kritik |
|-------|--------|
| **Var kommer confidence ifrån?** | Vapi/Deepgram returnerar transkript – vi måste verifiera om **word-level confidence** (eller alternativ) skickas med i webhook-payloaden. Om det **inte** finns i det vi får idag måste vi antingen byta/utöka Vapi-konfiguration eller acceptera att vi inte har confidence och **inte** bygga denna logik än. **Otydlighet i PDS:** exakt vilket fält i vilken payload? |
| **Vilka ord är "kritiska"?** | Alla produktnamn? Bara namnet på rätten eller också antal? Om vi nekar vid &lt; 0.6 på *ett* ord men resten är bra riskerar vi falskt negativ (irriterad kund). Om vi kräver 0.6 på *alla* produktord kan det bli för strikt. |
| **"Neka ordern"** | Idag returnerar vi `results` med success/error till Vapi. Om vi "nekar" måste vi returnera ett tydligt fel (t.ex. "Låg transkriptionssäkerhet för en eller flera rätter; bekräfta gärna igen") som Vapi-assistenten kan tolka och trigga en clarification loop. Det kräver att **system prompt / Vapi-flöde** är anpassat så att AI:n vet vad den ska säga. Annars får kunden bara ett generiskt fel. |

**Slutsats:** Confidence-gating är **bra i teorin** men **beroende av data vi kanske inte har**. Säkrast: (1) **Först** dokumentera eller logga exakt vad webhooken får från Vapi (hela payload eller relevant del). (2) Om word-level confidence **finns**, bygg en **enkel, tydlig** funktion: för varje order-item, om det finns en confidence för det namnet och den är under en tröskel (t.ex. 0.6), returnera ett specifikt fel till Vapi och **inte** spara order. (3) Om confidence **inte** finns, **lägg inte in** confidence-gating – då blir det bara gissning. Jag specificerar nedan ett konkret kodskiss för när confidence finns.

---

## Del 2: Den "smarta", skottsäkra lösningen

### 2.1 Caching utan att sälja gamla pizzor i 5 minuter

**Problem:** Cacha meny 5 min → pizzerian uppdaterar menyn men AI använder gammal meny.

**Lösning:**

- **TTL kort nog:** 2–3 minuter (inte 5) för meny/keywords-cache per restaurang. Balans: mindre DB-belastning, men snabb spridning av ändringar.
- **Invalidate vid menyändring:** Om ni i framtiden har ett admin-gränssnitt eller en webhook där pizzerian "sparar meny", anropa **samma** `/admin/tenants/{rest_id}/invalidate` (eller en dedikerad `invalidate-menu` för den rest_id). Då rensas config-cache; nästa anrop hämtar ny meny. Idag utan sådant gränssnitt: kort TTL räcker.
- **Ingen meny i DB idag:** Så länge menyn bara finns i `menu.json` behöver vi **ingen** meny-cache i backend för Diamond Polish. Keyword-injection kan göras med **samma** fil (läsa vid behov eller cacha i minnet med TTL 2–3 min från filens mtime eller en enkel in-memory cache). Det **påverkar inte** befintlig flöde negativt.

### 2.2 Konkret exempel: Confidence-Gating (fenomenalt tydlig)

Förutsättning: webhooken får per ord (eller per segment) en confidence. T.ex. `word_alternatives` eller `items[].confidence` i payloaden – **detta måste verifieras mot Vapi**.

```text
Pseudokod (tydlig, inte körbar utan exakt API):

def should_reject_order_low_confidence(
    order_items: list[dict],   # [{ "id": 1, "name": "Margherita", ... }]
    transcript_confidence: list[dict]  # [{ "word": "Margherita", "confidence": 0.4 }, ...]
) -> tuple[bool, str]:
    """
    Returnerar (True, orsak) om ordern ska nekas pga låg confidence på kritiskt ord.
    Returnerar (False, "") om OK.
    """
    CRITICAL_THRESHOLD = 0.6
    for item in order_items:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        for tc in transcript_confidence:
            if (tc.get("word") or "").strip().lower() == name.lower():
                if (tc.get("confidence") or 0) < CRITICAL_THRESHOLD:
                    return True, f"Låg säkerhet för '{name}' ({tc.get('confidence')}); be kunden bekräfta."
    return False, ""
```

- Anropas **endast** om vi faktiskt har `transcript_confidence` från Vapi.
- En tröskel (0.6), en tydlig orsak, inga magiska tal i flera ställen.
- Om Vapi inte skickar confidence: **anropas funktionen aldrig**; befintligt flöde oförändrat.

---

## Del 3: Fullständig implementationsplan (konservativ, steg-för-steg)

### Princip

- **Inget tas bort**, inget befintligt beteende ändras till det sämre.
- **Nya saker är tillägg:** valfria parametrar, nya endpoints eller bakgrundsanrop som vid fel alltid loggar + alertar.

### Fas A: Förberedelser (ingen beteendeändring)

1. **Dokumentera Vapi-payload**  
   Logga (eller dokumentera) en full webhook-payload från Vapi för ett riktigt tool-calls-anrop. Kontrollera om det finns **word-level confidence** eller liknande. Om ja → planera confidence-gating; om nej → **hoppa över** confidence-gating tills Vapi/Deepgram levererar det.

2. **Meny/keywords**  
   Om menyn fortsatt ligger i `menu.json`: bygg en **liten** in-memory cache (rest_id → lista unika produktnamn, TTL 2–3 min). Använd den **endast** för att exponera keywords till Vapi om ni lägger till ett anrop vid samtalstart – **ändra inte** `/menu` eller place_order-validering till att kräva denna cache. Så inget negativt påverkar nuvarande flöde.

### Fas B: BackgroundTask för SMS (säkert)

1. **Spara order exakt som idag** synkront (orders.json + Supabase insert oförändrat).
2. **Lägg till** FastAPI `BackgroundTasks` i webhook-endpointen. Efter att order sparats och **innan** du returnerar `JSONResponse(content={"results": ...})`, lägg till en task: `background_tasks.add_task(send_sms_and_alert_on_failure, order, customer_phone, rest_id)`.
3. **Funktionen** `send_sms_and_alert_on_failure`: anropar `send_sms_order_confirmation(order, customer_phone)`. Om retur är `False` eller om undantag: anropa **samma** alert-kanal som circuit breaker (PUSHOVER_ALERTS_*) med meddelande typ: `[ALERT] SMS misslyckades – order_id X, rest_id Y, fel: Z`. Ingen ändring av DB-schema.
4. **Pushover (köksnotis)** kan antingen stanna kvar synkront (snabbt) eller flyttas till samma BackgroundTask. Om vi flyttar: samma felhantering – vid fel, alert till admin.

**Förbättring i millisekunder:**  
Vapi får 200 + `results` direkt efter att order sparats och köksnotis skickats (om vi behåller Pushover synkront). SMS-latens (Vonage, ofta 500–2000 ms) påverkar inte längre webhook-svarstiden. Typisk besparing: **ca 500–2000 ms** på svarstid till Vapi, beroende på Vonage.

**Nya risker och motåtgärder:**

| Risk | Motåtgärd |
|------|------------|
| SMS körs aldrig (process dör efter 200, före task) | Accepterat; admin får ingen alert om processen kraschar. Minskning: logga "SMS scheduled" (order_id) så att vid manuell granskning kan man se att task lades till. Vid fel i task får admin alltid alert. |
| Event loop blockad vid många samtidiga tasks | Behåll task enkel: en HTTP-post till Vonage, en eventuell post till Pushover. Ingen tung DB-jobbar i samma task. Om vi senare ser problem: begränsa antal samtidiga SMS-tasks (kö eller semafor). |
| Minne | En task är bara en referens till funktion + argument; försumbar. Ingen ny cache som växer obegränsat. |

### Fas C: Confidence-Gating (endast om data finns)

1. Efter att ha bekräftat att webhooken får confidence-data: lägg till en funktion enligt pseudokoden ovan.
2. I webhooken, **efter** att vi byggt `order` och **före** `_process_place_order` / sparande: anropa `should_reject_order_low_confidence(...)`. Om `True`: returnera 200 med `results` som innehåller ett tydligt fel till Vapi (så att AI kan gå in i clarification loop); **spara inte** order.
3. Tröskel (0.6) ska vara konfigurerbar (env eller konstant högst upp).

**Förbättring:** Färre felbeställningar pga fel transkribering; ingen försämrad latens om vi bara gör en linjär genomgång av ord.

**Risk:** Falskt negativ (bra order nekas). Minskning: börja med tröskel 0.5; dokumentera och justera efter riktiga samtal.

### Fas D: Keyword-Injection (valfritt, senare)

1. Om ni lägger meny i DB: cacha meny per rest_id med TTL 2–3 min; bygg keyword-lista (max 30–50 ord) från produktnamn; exponera till det som startar samtalet (Vapi call-assistant eller motsvarande). **Kräver** att vi vet exakt när/hur Vapi tar emot keywords (per call eller per assistant).
2. Om menyn ligger kvar i fil: läs från fil (eller fil-cache med mtime/TTL); bygg lista; skicka till Vapi om ni har ett anrop vid samtalstart. **Ingen** ändring av place_order eller webhook-svar.

---

## Del 4: Otydligheter i PDS som Cursor vill ha klargjorda

1. **"Vid samtalets början"** – Menar Gemini: (a) en webhook som Vapi anropar när ett samtal startar (call.started?), eller (b) första anropet till vår webhook som råkar vara tool-calls? Om (a) krävs att vi exponerar en separat endpoint eller att Vapi kan skicka metadata vid första meddelandet. Om (b) har vi redan rest_id och kan i samma request läsa meny – men då är det inte "före" samtalet utan i första tool-calls-batch.

2. **"Draft"** – Ska ordern sparas med status "draft" och sedan uppdateras till "confirmed" när SMS skickats? Det introducerar ett nytt tillstånd och behov av retry/cleanup. Cursors rekommendation: **spara inte draft**; spara order som "klar" direkt (som idag) och hantera endast "SMS skickad ja/nej" via logg + admin-alert vid fel.

3. **Confidence-fält** – Exakt vilket fält i Vapi/Deepgram webhook-payload används för word-level confidence? Namn och sökväg så att Cursor kan skriva exakt kod utan att gissa.

---

## Sammanfattning för dig (prioritet)

- **Kritik:** Keyword-injection är bra men måste begränsas (antal, TTL) och får inte blockera samtalstart. Pre-commit med "draft" skapar onödig komplexitet och risk för skräpdata; bättre: spara order som idag, flytta bara SMS (och eventuellt Pushover) till BackgroundTask med **alltid** admin-alert vid fel. Confidence-gating kräver att vi faktiskt får confidence från Vapi; annars bygger vi inte det.
- **Säkrast nästa steg:** (1) Implementera **endast** BackgroundTask för SMS + obligatorisk admin-notis vid SMS-fel. (2) Verifiera om Vapi skickar confidence; om ja, lägg in enkel confidence-gating med tydlig tröskel. (3) Keyword-injection som senare steg med kort TTL och begränsat antal ord, utan att ändra befintlig place_order-/webhook-logik negativt.
- **Garanti:** Ingen ändring som tar bort eller försämrar nuvarande beteende; nya saker är tillägg med tydlig felhantering och alert så att du ser om något går fel.
