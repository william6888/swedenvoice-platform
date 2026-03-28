# Sammanfattning: Allt som byggts sedan SAVE_POINT (enkelt språk)

**SAVE_POINT** = den äldre versionen som var ute på Railway innan vi byggde Fas 1, 2 och 3. Då hade ni redan: webhook som tar emot beställningar från Vapi, Sparande i Supabase, Pushover, SMS (Vonage), köksdashboard.

Det här dokumentet beskriver **vad som ändrats** sedan dess, **varför**, och **om det gick som planen**.

---

## I korthet: Vad har hänt?

Vi har byggt **tre lager** (Fas 1, 2, 3) ovanpå det som fanns. De gör att:

1. **En restaurang kan inte råka ta ner en annan** (Fas 1 – Safety Net).
2. **Varje restaurang kan få egna inställningar och (framöver) egna nycklar** (Fas 2 – Engine).
3. **Ni kan "stänga" en restaurang mjukt utan att radera ordrar** (Fas 3 – Livscykel).

Allt detta är nu **deployat på Railway** och **Supabase** är uppdaterad (deleted_at, restaurant_secrets, throttle-kolumner). Det gick i stort sett som planen; några saker är dokumenterade som "kända begränsningar" (t.ex. direct place_order, flera workers).

---

## Fas 1: Safety Net (säkerhetsnät)

**Vad det betyder för dig:**  
Om något går fel för *en* restaurang (t.ex. Supabase nere, fel konfiguration) ska inte *alla* restauranger påverkas. Och ni ska kunna stänga av en restaurang **omedelbart** om ni behöver.

### Ändringar som byggts

| Vad | Enkelt förklarat |
|-----|-------------------|
| **Aktiva-tenant-lista** | Servern håller en lista "vilka restauranger får ta emot beställningar just nu". Listan uppdateras från databasen var 1:e minut. Om en restaurang inte finns i listan → vi svarar "Restaurangen kunde inte hittas" istället för att försöka skapa order. |
| **Config-cache** | Istället för att fråga databasen *varje* gång någon ringer, sparar vi restauranginfo i minnet i 5 minuter. Snabbare och mindre belastning på DB. |
| **Circuit breaker** | Om en restaurang får många fel på kort tid (t.ex. 5 fel på 60 sekunder) stänger vi av *den* restaurangen i 60 sekunder. Andra restauranger påverkas inte. Ni får en **varning i Pushover** när det händer. |
| **Token bucket (throttling)** | Varje restaurang får inte skicka hur många anrop som helst. Det finns en "hink" med t.ex. 20 anrop; den fylls långsamt på. För många anrop → vi svarar "För många anrop, vänta en stund." så att ingen kan överbelasta systemet. |
| **Instant Kill (invalidate)** | Ni kan anropa en hemlig URL med en admin-nyckel och säga "den här restaurangen ska inte få fler anrop *nu*". Cacher och listor rensas direkt så att ingen ny beställning går igenom för den restaurangen. |

**Gick det som planen?** Ja. Allt ovan finns i koden, skyddat med `ADMIN_SECRET` (X-Admin-Key). Vid en felsökningsrunda la vi till att **invalidate** också rensar circuit breaker och token bucket för den restaurangen, så att minnet inte växer och gamla tillstånd inte ligger kvar.

---

## Fas 2: Engine (motorn)

**Vad det betyder för dig:**  
Förberedelser för att kunna ha **flera restauranger med egna inställningar**. Throttle (hur många anrop som tillåts) kan sättas per restaurang i databasen. Hemligheter (t.ex. Vonage/Pushover-nycklar) kan i framtiden lagras krypterat per restaurang.

### Ändringar som byggts

| Vad | Enkelt förklarat |
|-----|-------------------|
| **Tabell restaurant_secrets** | I Supabase finns en tabell där ni (i framtiden) kan lagra krypterade nycklar per restaurang. Idag används den inte för utskick än – Pushover/Vonage går fortfarande på globala nycklar i Railway. |
| **Kryptering (Fernet)** | Om ni sätter `ENCRYPTION_SECRET` i Railway kan backend kryptera/dekryptera det som ligger i restaurant_secrets. Då ligger inga klara lösenord i databasen. |
| **Throttle från DB** | På tabellen `restaurants` finns nu kolumner för hur stor "hinken" ska vara och hur snabbt den fylls (per restaurang). Om ni inte sätter något används standard (t.ex. 20 och 0.1). |
| **Config-cache inkl. secrets** | När vi läser restauranginfo från DB kan vi nu också hämta (och dekryptera) eventuella hemligheter och cacha dem. När ni senare använder per-tenant Pushover/Vonage räcker det att backend läser från denna cache. |

**Gick det som planen?** Ja. SQL för Fas 2 (supabase_fas2_restaurant_secrets.sql) är kört. Vid felsökning fixade vi så att vi **aldrig** returnerar config för en restaurang som är "soft-deleted" (Fas 3), även om en nätverksfallback användes.

---

## Fas 3: Livscykel

**Vad det betyder för dig:**  
Ni ska kunna **stänga en restaurang** (ta bort den från tjänsten) **utan att radera gamla ordrar**. Ordrar ska sparas (t.ex. för bokföring/lagkrav). När ni "stänger" en restaurang ska den sluta få beställningar direkt (Instant Kill) och i databasen markeras med ett datum (soft delete).

### Ändringar som byggts

| Vad | Enkelt förklarat |
|-----|-------------------|
| **Kolumnen deleted_at** | På tabellen `restaurants` i Supabase finns nu en kolumn `deleted_at`. Om den är tom (NULL) = restaurangen är aktiv. Om ni sätter ett datum = restaurangen räknas som borttagen och får inga fler anrop (listan "aktiva tenants" hämtar bara där deleted_at är NULL). |
| **Soft-delete-URL** | Ni kan anropa en skyddad URL som gör två saker: (1) Instant Kill för den restaurangen, (2) sätter `deleted_at = nu` i databasen. Då behöver ni inte gå in i Supabase manuellt för att sätta deleted_at. |
| **Ingen CASCADE på orders** | När ni stänger en restaurang raderas **inte** deras ordrar. De finns kvar. Endast kopplade saker som "secrets" och "members" kan tas bort med restaurangen (det var redan så i Fas 2). |
| **Återaktivering** | Om ni vill "sätta på" en restaurang igen kan ni i Supabase köra: sätt `deleted_at = NULL` för den restaurangen. Inom max 1 minut räknas den som aktiv igen. |

**Gick det som planen?** Ja. Du körde `supabase_fas3_deleted_at.sql` i Supabase. Backend använder nu `deleted_at IS NULL` överallt där vi kollar "är denna restaurang aktiv?". Om ni anropar soft-delete utan Supabase konfigurerat får ni ett tydligt meddelande istället för att det bara ser ut som om allt gick bra.

---

## Övriga fixar under felsökning

- **Invalidate rensar allt** för den restaurangen: config-cache, call-cache, **och** circuit breaker + token bucket, så att inget gammalt tillstånd ligger kvar.
- **Fallback-queries** (när första DB-anropet misslyckas) använder också "bara aktiva restauranger" (deleted_at IS NULL), så vi ger aldrig tillbaka info om en borttagen restaurang.
- **Direct place_order** (anrop med bara `{"items": [...]}` utan Vapi-format) går medvetet **inte** genom Fas 1–3 – det är dokumenterat som känd begränsning för enkla/direkta anrop.

---

## Gick allt som planen / som jag tänkt mig?

**Ja, i stort sett.**

- **Fas 1:** Safety Net med aktiva-lista, cache, circuit breaker, token bucket, Instant Kill och Pushover-alert är byggt och deployat. Invalidate rensar nu även circuit breaker och token bucket.
- **Fas 2:** Tabell och kryptering för secrets, throttle från DB, config som kan inkludera secrets – allt finns. Per-tenant Vonage/Pushover är **inte** byggt än (planerat som nästa steg när ni vill).
- **Fas 3:** Soft delete med `deleted_at`, admin soft-delete-URL, och att vi aldrig serverar borttagna restauranger – byggt och kört i Supabase. Hard delete av ordrar efter X år är inte byggt (kan göras som script/admin senare).

**Kända begränsningar** (inga buggar, bara så systemet är upplagt idag):

- Direct `/place_order` utan Vapi-format går inte genom tenant-check/circuit breaker/throttle.
- Pushover/Vonage använder fortfarande globala nycklar; per-tenant nycklar från `restaurant_secrets` används inte än.
- Om Railway kör flera "workers" delas inte minnet – då gäller Instant Kill bara på den worker som fick anropet; andra workers följer efter max 1 minut via DB-uppdatering.

---

## Snabbordlista: Vad du har nu

| Funktion | Hur du använder det |
|----------|----------------------|
| **Stänga en restaurang direkt** | `POST .../admin/tenants/Gislegrillen_01/soft-delete` med header `X-Admin-Key: <din ADMIN_SECRET>`. |
| **Bara rensa cacher (utan att sätta deleted_at)** | `POST .../admin/tenants/Gislegrillen_01/invalidate` med samma admin-nyckel. |
| **Varning när något går fel för en restaurang** | Sätt `PUSHOVER_ALERTS_USER_KEY` och `PUSHOVER_ALERTS_TOKEN` i Railway (eller använd samma som vanlig Pushover) – då får ni notis när circuit breaker öppnas. |
| **Återaktivera en soft-deleted restaurang** | I Supabase SQL: `UPDATE restaurants SET deleted_at = NULL WHERE external_id = 'Gislegrillen_01';` |

Om du vill kan nästa steg vara t.ex. **per-tenant Vonage/Pushover** (använda nycklar från `restaurant_secrets`) eller ett **enkelt script/admin för hard delete** av ordrar efter X år.
