# Problem just nu – och hur vi fixar dem

Kort översikt: vilka problem som finns, vad våra senaste ändringar kan ha orsakat, och konkreta åtgärder. **Backend är nu tolerant:** om kolumnen `special_instructions` saknas sparas order ändå (utan det fältet), och vid start varnar vi om Supabase restaurants returnerar 0 rader (RLS/anon).

---

## 1. Problem som finns just nu

| Problem | Konsekvens | Åtgärd |
|--------|------------|--------|
| **Supabase `orders` saknar kolumnen `special_instructions`** | **Mildrad:** Backend försöker först med full rad; om insert felar p.g.a. saknad kolumn görs **automatisk fallback** utan special_instructions och notes. Order sparas då ändå. För full funktion (Lovable visar specialönskemål) kör ALTER TABLE. | Kör **en gång** i Supabase SQL Editor: `ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS special_instructions text;` (fil: `SUPABASE_ADD_SPECIAL_INSTRUCTIONS.sql`). |
| **Backend använder anon-nyckel mot Supabase** | Efter RLS på `restaurants` och `restaurant_members`: anon får inte läsa dessa tabeller. Backend får 0 rader vid lookup. **Vid start** skriver backend nu en varning om restaurants returnerar 0 rader. | Sätt i **Railway → Variables** `SUPABASE_KEY` till **service_role**-nyckeln (Supabase → Project Settings → API → service_role). |
| **`raw_transcript` ofta tom i databasen** | Inte ett "fel" – Vapi skickar inte alltid transkript i samma webhook som place_order. | Acceptera att fältet ofta är tomt, eller senare koppla in Vapi-event med transkript. |
| **Orders är öppna för anon (RLS policy USING true)** | Medvetet tills Lovable använder Auth. | Låt vara; när Lovable har Auth, strama åt policy på orders. |
| **Känslig kolumn `api_key` i `restaurants`** | RLS begränsar redan åtkomst. | För extra säkerhet: flytta till restaurant_secrets eller ta bort om oanvänd. |

---

## 2. Problem som våra senaste ändringar kan ha orsakat

| Ändring | Möjligt problem | Hur vi fixar / undviker |
|---------|------------------|--------------------------|
| **Vi skickar nu `special_instructions` till Supabase** | Om kolumnen inte finns gör backend **automatisk fallback** (sparar utan special_instructions/notes). Order sparas ändå. | Kör ALTER TABLE för att få full funktion (Lovable visar specialönskemål). |
| **Vi skickar `notes` per rad i `items`-JSON** | Ovanligt att det bryter något – JSONB accepterar extra nycklar. Om Lovable validerar `items` strikt och kräver bara vissa fält kan de ignorera `notes` eller vi kan ta bort det om ni vill. | Ingen åtgärd behövs om Lovable inte klagar. Om ni vill ta bort notes: vi kan sluta skicka det (en rad i main.py). |
| **RLS aktiverat på restaurants + restaurant_members** | Om backend fortfarande använder **anon**: läsningar från dessa tabeller returnerar 0 rader → tenant-lookup faller, order kan sparas med fel eller ingen restaurant_uuid. | Se ovan: använd **service_role** i Railway. Verifiera med ett testanrop (ring eller test_order) och kolla att ordern sparas i Supabase med rätt restaurant_id/restaurant_uuid. |

---

## 3. Så att det inte blir problem framöver

**Innan deploy / efter kodändringar som rör Supabase:**

1. **Kolla att `special_instructions` finns**  
   Kör i Supabase:  
   `SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'orders' AND column_name = 'special_instructions';`  
   Om det returnerar en rad är kolumnen på plats.

2. **Kolla att Railway använder service_role**  
   I Railway Variables: `SUPABASE_KEY` ska vara **service_role**-nyckeln (börjar ofta med `eyJ...` som JWT; anon och service_role ser likadana ut – kolla i Supabase Dashboard vilken du kopierat).

3. **Efter RLS-ändringar**  
   Alltid testa: lägg en order (Vapi eller direkt anrop), kontrollera i Supabase Table Editor att raden finns med rätt restaurant_id/restaurant_uuid och att Lovable visar ordern.

**Dokumentation:**

- **ONBOARDING_NY_PIZZERIA.md** – när ni lägger till ny pizzeria, inkl. att backend använder samma Supabase och service_role.
- **SUPABASE_SAKERHET_AGENT_PLAN.md** – RLS och policies; att inte ändra anon på orders tills Lovable har Auth.
- **SUPABASE_ADD_SPECIAL_INSTRUCTIONS.sql** – kör en gång per databas där ni har `orders`.

**Kort checklista (rekommenderat):**

- [ ] Railway SUPABASE_KEY = service_role (inte anon). Vid start ska det **inte** stå att restaurants returnerade 0 rader.
- [ ] ALTER TABLE för `special_instructions` kördd i Supabase (för att Lovable ska kunna visa specialönskemål; utan den sparas order ändå tack vare fallback).
- [ ] Ett testanrop: order sparas i Supabase. Om kolumnen finns: special_instructions och (vid behov) raw_transcript ifyllda.
- [ ] Lovable visar ordern och (när ni visar det i UI) special_instructions.

Backend är nu tolerant: saknad kolumn ger fallback, och startvarning vid misstänkt fel nyckel. När checklistan är uppfylld är lösningen stabil.
