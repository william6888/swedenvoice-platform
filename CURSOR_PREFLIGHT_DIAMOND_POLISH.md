# Pre-flight: Är jag 100 % säker? (Cursor → dig som chef)

Du frågar om jag verkligen är **helt säker** och om lösningarna är **genomtänkta**, och vill att jag **undersöker vidare** och **identifierar problem** innan vi börjar. Här är den ärliga bedömningen.

---

## Vad jag är trygg med (kan koda utan att gissa)

### 1. BackgroundTask för SMS + Admin Failure Alert

- **FastAPI BackgroundTasks** körs efter att responsen skickats; Vapi får 200 direkt. Det är dokumenterat och stabilt.
- Vi behåller **exakt** samma ordning: spara order → Pushover (synkront) → lägg SMS som bakgrundstask → returnera results. Ingen ändring av när eller hur order sparas.
- Vi kan skicka **Order**-objektet till tasken (referensen är giltig tills tasken kört klart). Som extra säkerhet kan vi skicka `order.model_dump()` + `customer_phone` + `rest_id` och i tasken bygga ett minimalt objekt för SMS-text + alert – då är vi helt oberoende av request-scope.
- **Alert vid SMS-fel:** Vi har redan `PUSHOVER_ALERTS_*` och `_send_circuit_breaker_alert`. En ny hjälpfunktion som anropar samma Pushover med meddelande typ `[ALERT] SMS misslyckades – order_id X, rest_id Y, fel: Z` – ingen ny infrastruktur.
- **Risk som kvarstår:** Om processen kraschar *direkt* efter att vi skickat 200 men *innan* tasken hunnit köras, skickas varken SMS eller alert. Det kan vi inte lösa med bara BackgroundTasks; det är accepterat och redan nämnt i kritikdokumentet.

**Slutsats:** Ja, jag är säker på denna del. Noll sidoskador på befintlig order-/webhook-logik.

---

### 2. Payload-logging för confidence

- Vi loggar redan `body.get("message", {})` och event_type. Att **utöka** med en rad som loggar t.ex. `message.get("transcript")` eller `message.get("transcriptWithConfidence")` (eller hela `message` vid tool-calls, begränsat till t.ex. 2000 tecken) – riskfri.
- **Risk:** Stor payload kan ge mycket loggutskrift. **Motåtgärd:** Logga bara om `event_type == "tool-calls"` och truncera till 1500–2000 tecken, eller logga bara nycklar som innehåller "transcript" eller "confidence".

**Slutsats:** Ja, säker. Vi kan inte *använda* confidence för gating förrän vi sett att fältet finns; loggningen ger oss det.

---

## Vad jag vill förtydliga innan jag lovar "fungerar garanterat"

### 3. Keyword Injection "i Vapi-konfigurationen"

**Problemet:** Vår backend blir anropad av Vapi vid **tool-calls** (och end-of-call-report). Vi har **ingen** webhook som anropas "vid samtalets början". Därför kan vi **inte** från nuvarande webhook "injektera keywords i Vapi" under pågående samtal – samtalet har redan startat med den konfiguration Vapi redan hade.

**Vad som faktiskt finns (enligt Vapi):**

- Vid **inbound-samtal utan förvald assistant** skickar Vapi en **assistant-request** till din Server URL. Då kan vi **svara med assistant-konfiguration** (inkl. transcriber med keywords) på **per-anrop-basis**. Det finns en **tidsgräns ~7,5 s** för att svara.
- Om ni i stället använder **en fast assistant** (samma för alla samtal) anropas inte assistant-request; då finns det ingen "call start"-webhook från Vapi till oss där vi kan returnera keywords.

**Därför:**

- Jag kan **säkert** bygga:
  - **Meny-cache** i minnet (TTL 3 min) baserat på `menu.json` (samma data som idag, bara cachad).
  - En **endpoint** t.ex. `GET /api/keywords?rest_id=Gislegrillen_01` som returnerar en lista unika produktnamn (och ev. uppdelade i enkla ord för Deepgram keywords) från cachen.
- Jag **kan inte** garantera att "AI:n känner igen lokala pizzanamn med hög precision" **enbart** med backend-ändringar, eftersom:
  - **Antingen** måste ni i Vapi konfigurera **assistant-request** till vår Server URL, och vi måste då implementera en **annan** endpoint (t.ex. `POST /vapi/assistant-request`) som svarar inom 7,5 s med assistant + transcriber.keywords från vår cache – **det går att koda**, men kräver att ni faktiskt använder assistant-request i Vapi.
  - **Eller** så använder ni GET /api/keywords manuellt eller via något annat system som uppdaterar Vapi-assistentens transcriber-keywords (t.ex. periodiskt). Då är backend klar, men "injection" sker utanför vår kod.

**Jag vill inte lova "keyword injection som bara fungerar"** utan att veta vilket av dessa ni använder. Om ni redan har assistant-request kan jag bygga endpoint + cache så att vi svarar med keywords. Om ni har fast assistant kan jag bara bygga cache + GET /api/keywords och dokumentera hur ni kopplar det till Vapi.

**Förtydligande till dig:** Ska jag (A) implementera **cache + GET /api/keywords** och dokumentera att ni antingen använder assistant-request eller manuell/periodisk uppdatering i Vapi, eller (B) **även** bygga en **POST /vapi/assistant-request**-handler som svarar med assistant inkl. keywords (om ni tänker använda assistant-request)? Om (B) måste ni ha Server URL för assistant-request pekande på oss och rest_id tillgänglig i den requesten (t.ex. från telefonnummer eller annan metadata).

---

## Justerad plan (så att inget negativt händer)

### Fas 1 (gör först – fullt säkra)

1. **BackgroundTask för SMS**
   - I webhooken: efter att order sparats och Pushover skickats, anropa `background_tasks.add_task(send_sms_with_alert_on_failure, order.model_dump(), customer_phone, rest_id)`.
   - `send_sms_with_alert_on_failure(order_dict, customer_phone, rest_id)`: bygg `Order(**order_dict)` eller en minimal representation, anropa `send_sms_order_confirmation`. Vid `False` eller exception: anropa befintlig alert-kanal (samma som circuit breaker) med order_id, rest_id och felmeddelande.
   - **Samma steg** i `/place_order` om det finns en Vapi-format-gren som också skickar SMS (så att båda vägarna är konsekventa).
   - Ingen ändring av `_process_place_order`, `_insert_order_to_supabase` eller returformat till Vapi.

2. **Payload-logging för confidence**
   - Vid `event_type == "tool-calls"`: logga en kompakt representation av `message` (eller bara nycklar som innehåller "transcript"/"confidence") med truncering (t.ex. 1500 tecken) så att vi kan utvärdera om confidence finns och var.

### Fas 2 (efter förtydligande om Vapi)

3. **Meny-cache (TTL 3 min)**
   - In-memory cache: nyckel t.ex. `"menu"` eller `rest_id` om menyn blir per tenant senare; värde = resultat av `load_menu()`; TTL 180 s. Vid cache-träff returnera cachad; vid miss anropa `load_menu()` och cacha.
   - **Användning:** `get_menu()` och `find_menu_item()` kan använda denna cache istället för att alltid läsa fil. Det **ändrar inte** beteende (samma data), bara färre filläsningar. Om `menu.json` ändras utan att processen startas om är data max 3 min gamla – redan accepterat.

4. **Keywords-endpoint**
   - Bygg lista unika produktnamn från menyn (alla kategorier, `item["name"]`). Returnera som JSON, t.ex. `{"keywords": ["Margherita", "Kebabpizza", ...]}`.
   - Endpoint: `GET /api/keywords?rest_id=Gislegrillen_01` (rest_id kan ignoreras tills menyn är per-tenant; då använder vi rest_id för cache-nyckel).
   - **Ingen** automatisk "injection" i Vapi från vår sida utan att vi har en assistant-request-handler; dokumentation om hur ni kopplar detta till Vapi (assistant-request eller manuell/periodisk konfiguration).

5. **Valfritt – assistant-request (endast om ni använder det)**
   - Om ni bekräftar att ni har (eller ska sätta) assistant-request mot vår Server URL: implementera `POST /vapi/assistant-request` (eller den path Vapi förväntar sig) som läser rest_id från bodyn, hämtar keywords från cachen, och svarar med assistant-objekt inkl. transcriber.keywords inom 7,5 s. Annars hoppar vi över detta steg.

---

## Sammanfattning för dig som chef

- **Ja** till att jag är **säker på**: BackgroundTask för SMS + admin-alert vid fel, och payload-logging för confidence. Det påverkar inte befintlig orderlogik eller Vapi-svar negativt.
- **Förtydligande behövs** kring keyword injection: jag bygger cache + GET /api/keywords och (om ni vill) assistant-request-handler, men "injection i Vapi-konfigurationen" beror på hur era samtal startar (assistant-request vs fast assistant). Jag lovar inte "hög precision på pizzanamn" utan att den kopplingen är gjord.
- **Planen är justerad** så att Fas 1 (SMS + logging) är helt säker och går att koda direkt; Fas 2 (cache + keywords) är också säker; själva "Vapi får keywords vid samtalstart" kräver antingen assistant-request-endpoint eller er konfiguration i Vapi.

Om du godkänner detta kan jag börja med Fas 1 (BackgroundTask + alert + payload-logging). Om du samtidigt kan svara hur ni startar samtal (fast assistant vs assistant-request) kan jag anpassa Fas 2 så att keyword-delen verkligen når Vapi som tänkt.
