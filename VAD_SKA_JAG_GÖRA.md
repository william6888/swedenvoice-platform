# Vad ska jag göra? – Steg för steg

Denna guide säger exakt vad **du** ska göra, vad du ska **skriva till Supabase**, vad du ska **skriva till Lovable**, och om någon annan behöver inblandas.

---

## Just nu (idag) – inget måste ändras

Systemet fungerar: ordrar sparas i Supabase med `restaurant_id` och `restaurant_uuid`, Lovable visar ordrar, FK och RLS är på plats. Du behöver **inte** skriva till Supabase eller Lovable om allt fungerar som du vill.

---

## Vad mer att kolla (valfritt)

Om Lovable och Supabase redan visar rätt beställningar behöver du inte göra mer för att vara “klar”. Om du vill dubbelkolla:

| Vad | Hur |
|-----|-----|
| **Kök / ordrar** | Syns nya ordrar i Lovable/Supabase och ev. `/dashboard`? Köksbong i Railway-loggar? |
| **SMS till kund** | Får kunden orderbekräftelse via Vonage? (Kräver att Vapi skickar kundens nummer i webhook.) |
| **Riktigt samtal** | Ring via Vapi-assistenten, lägg en order, kolla att den syns i Lovable med rätt innehåll. |
| **Tenant-lookup** | Öppna `https://<railway-url>/debug-tenant?rest_id=Gislegrillen_01` → ska visa `restaurant_id`, `restaurant_uuid`, `lookup_ok: true`. |
| **Call-cache** | Efter ett riktigt samtal: `GET /debug-call-cache` → visar om call_id → restaurant sparas (valfritt att kolla). |

---

## Nästa steg (i prioritetsordning)

1. **Gå live med Gislegrillen**  
   Använd nuvarande setup. Vapi Server URL med `?rest_id=Gislegrillen_01`, en rad i `restaurants` med `external_id = Gislegrillen_01`. Inget mer behövs för en kund.

2. **När ni tar in nästa restaurang**  
   - Supabase: ny rad i `restaurants` med t.ex. `external_id = 'PizzeriaX_01'`, `name = 'Pizzeria X'`.  
   - Vapi: skapa en ny assistent (eller duplicera) för den kunden; sätt Server URL till samma webhook men med `?rest_id=PizzeriaX_01`.  
   - Lovable: antingen (a) samma köksvy där användaren väljer restaurang / loggar in och ser sin via `restaurant_members`, eller (b) separat “projekt”/filter per kund.  
   Backend behöver **ingen** ändring – den är redan tenant-blind.

3. **Staging (rekommenderat innan många kunder)**  
   En extra Railway-service som deployar från t.ex. `develop`, egen URL. En testassistent i Vapi som pekar på Staging-URL. Testa ändringar där innan deploy till production.

4. **Övervakning**  
   Titta på Railway (minne, loggar) och Supabase (användning) då och då. Vid fler kunder: health check (`/health`), ev. enkel alert vid fel.

5. **Lovable multi-tenant på riktigt**  
   När flera restauranger ska använda samma köksvy: användare loggar in, kopplas till restaurang via `restaurant_members`, edge-funktionen filtrerar ordrar på den inloggade användarens `restaurant_id`/`restaurant_uuid`. Det är konfiguration/frontend i Lovable, inte backend-ändring.

---

## 1. Vad DU ska göra (själv)

### Kontinuerligt
- **Railway:** Se till att variabeln `RESTAURANT_UUID` är satt (du har redan satt den). Om du skapar nytt projekt/deployment, lägg till den igen.
- **Lokal .env:** Ha `RESTAURANT_UUID=bd525e53-cfb0-4818-a666-90664cd8414f` i `.env` när du kör backend lokalt.
- **Test:** När du vill kolla att ordrar kommer fram: kör `python3 test_order_railway.py`. Kolla sedan i Supabase (Table Editor → orders) och i Lovable (köksvy, inloggad) att ordern syns.

### Inget du behöver göra just nu
- Du behöver **inte** ändra `test_order.py` eller `test_order_railway.py`.
- Du behöver **inte** be någon stänga anon SELECT eller ändra RLS än.

---

## 2. Vad du ska skriva till SUPABASE (när det behövs)

Använd Supabase-chatten (eller support) och klistra in nedan. Du skriver till Supabase **bara när** du ska göra något av det här; annars behöver du inte skriva till dem.

---

### A) Du vill bara dubbelkolla att allt är OK

**Klistra in:**

```
Kan du verifiera följande för projektet (public.orders)?

1. Finns kolumnen restaurant_uuid (uuid, NOT NULL) och har alla rader ett uuid?
2. Finns foreign key orders_restaurant_uuid_fkey mot public.restaurants(id)?
3. Finns det fortfarande en anon SELECT-policy på orders (så att vår edge-funktion kan läsa med anon)?

Svara med kort punktlista (OK / saknas / fel).
```

---

### B) När du ska lägga till en NY restaurang (t.ex. Restaurang B)

**Klistra in:**

```
Jag ska lägga till en ny restaurang (multi-tenant).

1. Skapa en ny rad i public.restaurants med:
   - external_id: [t.ex. "RestaurangB_01" eller det ID ni vill använda]
   - name: [restaurangens namn]

2. Ge mig sedan UUID (id) för den nya raden så att jag kan använda den i backend/env.

3. Om jag ska använda Supabase Auth för inloggning till köksvy för denna restaurang:
   - Jag skapar (eller har) en användare i Auth.
   - Lägg till en rad i public.restaurant_members som kopplar den användarens auth_user_id till den nya restaurangens id (restaurant_id) med lämplig role (t.ex. "owner").
```

Ersätt `[t.ex. ...]` med dina egna värden innan du skickar.

---

### C) Om något gick sönder – anon SELECT försvann och Lovable visar inga ordrar

**Klistra in:**

```
Vår edge-funktion läser från public.orders med anon-nyckeln. Lovable visar inga ordrar – har anon SELECT-policy på orders tagits bort?

Om ja: Lägg tillbaka en policy så att anon kan SELECT på public.orders. T.ex.:

CREATE POLICY "anon_select_on_orders" ON public.orders
FOR SELECT TO anon USING (true);

Kör detta och bekräfta när det är gjort.
```

---

### D) Du vill INTE att Supabase gör något

Om allt fungerar: **skriv inget till Supabase.** Du behöver inte bekräfta något varje vecka.

---

## 3. Vad du ska skriva till LOVABLE (när det behövs)

Du skriver till Lovable (Lovable AI / support) **bara när** du ska bygga om något i appen. Annars behöver du inte skriva till dem.

---

### A) Allt fungerar – du vill bara veta att de inte ska ändra något

**Klistra in (om du vill vara tydlig):**

```
Vår köksvy hämtar ordrar via edge-funktionen get-external-orders från extern Supabase (zgllqocecavcgctbduip). Den filtrerar på restaurant_id = 'Gislegrillen_01'.

För Gislegrillen ska inget ändras: behåll anropet till get-external-orders och filtreringen på Gislegrillen_01. Vi lägger inte till fler restauranger i denna app just nu.
```

---

### B) När du ska lägga till FLERA restauranger (flera köksvyer / filter)

**Klistra in:**

```
Vi ska stödja flera restauranger i samma app.

Idag: Edge-funktionen get-external-orders hämtar ordrar från extern Supabase och filtrerar på restaurant_id = 'Gislegrillen_01'.

Behöver:
1. Köksvyn ska kunna visa ordrar för olika restauranger. Antingen:
   - användaren väljer vilken restaurang (dropdown eller liknande), och edge-funktionen tar emot denna parameter och filtrerar på motsvarande restaurant_id eller restaurant_uuid, ELLER
   - varje inloggad användare är kopplad till en restaurang (via vår externa Supabase restaurant_members), och ni hämtar endast ordrar för den användarens restaurang.

2. Behåll anrop till get-external-orders mot samma externa Supabase (zgllqocecavcgctbduip). Ändra bara så att filtrering sker per restaurang (enligt punkt 1).

3. Om ni behöver restaurant_id eller restaurant_uuid för filtrering: vi har båda i orders-tabellen. external_id i restaurants motsvarar t.ex. 'Gislegrillen_01'; id (uuid) är restaurant_uuid.
```

---

### C) Lovable visar inga ordrar – felsökning

**Klistra in:**

```
Köksvyn visar inga ordrar trots att vi har ordrar i extern Supabase (zgllqocecavcgctbduip).

Kan ni:
1. Bekräfta att köksvyn anropar get-external-orders (och inte läser direkt från Lovable Cloud)?
2. Kontrollera att edge-funktionen get-external-orders filtrerar på restaurant_id = 'Gislegrillen_01' (eller visar alla om det inte finns filter)?
3. Testa edge-funktionen manuellt och visa svar (antal ordrar). Om den returnerar [] – varför?
4. Kräver köksvyn inloggning? Om ja – måste användaren vara inloggad för att ordrar ska laddas?
```

---

### D) Du vill INTE att Lovable gör något

Om köksvyn visar ordrar och du inte ska lägga till fler restauranger ännu: **skriv inget till Lovable.**

---

## 4. Andra (Vapi, Railway m.m.)

### Vapi
- **Normalt:** Du behöver inte skriva till Vapi. Webhook-URL pekar på Railway; place_order anropas vid samtal.
- **Om ordrar inte kommer fram vid samtal:** Kontrollera i Vapi Dashboard att Server URL är `https://web-production-a9a48.up.railway.app/vapi/webhook` och att place_order anropas (Logs). Skriv till Vapi support om webhook inte når Railway.

### Railway
- **Normalt:** Du behöver inte skriva till Railway. Du sätter bara Variables i dashboarden.
- **Om deploy misslyckas eller appen kraschar:** Kolla Logs i Railway. Säkerställ att SUPABASE_URL, SUPABASE_KEY och RESTAURANT_UUID är satta.

### Cursor (mig)
- När du ska **ändra backend-kod** (t.ex. stöd för flera restauranger utifrån webhook), säg till här: "Vi ska lägga till Restaurang B – backend ska bestämma restaurang från Vapi assistantId och skicka rätt restaurant_uuid." Då kan jag föreslå konkreta kodändringar i main.py.

---

## 5. Snabböversikt – vem gör vad och när

| Situation | Du | Supabase | Lovable | Övrigt |
|-----------|----|----------|---------|--------|
| Allt fungerar | Inget. Kör test vid behov. | Inget. | Inget. | – |
| Dubbelkolla Supabase | – | Skicka text under 2A. | – | – |
| Lägga till ny restaurang (DB) | Bestäm external_id + namn. | Skicka text under 2B. | – | – |
| Köksvy för flera restauranger | Beskriv krav. | – | Skicka text under 3B. | – |
| Lovable visar inga ordrar | – | Eventuellt 2C om anon SELECT saknas. | Skicka text under 3C. | – |
| Backend för flera restauranger | Be Cursor ändra main.py. | – | – | – |

---

## 6. Sammanfattning

- **Idag:** Du behöver inte skriva till Supabase eller Lovable om allt fungerar.
- **Till Supabase** skriver du när du vill verifiera (2A), lägga till ny restaurang (2B) eller återställa anon SELECT (2C). Klistra in motsvarande text ovan.
- **Till Lovable** skriver du när du ska bygga fler restauranger i köksvyn (3B) eller felsöka att ordrar inte syns (3C). Klistra in motsvarande text ovan.
- **Till andra** (Vapi, Railway): normalt inget; vid problem kolla Dashboard/Logs eller be Cursor ändra backend.

All text ovan är avsedd att klistras in som den är (där du inte ska ersätta [ ] med egna värden).
