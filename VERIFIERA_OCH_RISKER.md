# Verifiering och risker – systemet idag + flera restauranger

## Test som körts (automatiskt)

| Test | Resultat |
|------|----------|
| **Railway webhook** (`python3 test_order_railway.py`) | ✅ 200 OK – order processad, svar med order_id. Backend tar emot, skickar till Supabase (med restaurant_id + restaurant_uuid). |

---

## Verifiering du bör göra manuellt

### 1. Supabase – senaste ordern har båda fälten
- **Supabase Dashboard** → Table Editor → **orders**
- Sortera på **created_at** DESC
- Kontrollera senaste raden:
  - **restaurant_id** = `Gislegrillen_01` (text)
  - **restaurant_uuid** = `bd525e53-cfb0-4818-a666-90664cd8414f`
- Om båda är ifyllda → backend + migration fungerar.

### 2. Lovable – ordrar syns i köksvyn
- Logga in på **swedenvoice.lovable.app** (eller preview) med williamsandseryd@icloud.com
- Öppna köksvyn
- **Förväntat:** Ordrar visas i NYA (inkl. den från test_order_railway.py om den inte flyttats)
- Om inget syns: kolla att du är inloggad; edge-funktionen använder fortfarande anon och filtrerar på `restaurant_id = 'Gislegrillen_01'`

### 3. Vapi (valfritt)
- Ring in ett kort testanrop, lägg en order
- Kontrollera att ordern dyker upp i Supabase och i Lovable

---

## Nuvarande arkitektur (en restaurang)

| Komponent | Beteende idag |
|-----------|----------------|
| **Backend** | `_get_restaurant_id_from_webhook()` returnerar alltid `"Gislegrillen_01"`. `RESTAURANT_UUID` från env skickas som `restaurant_uuid` vid insert. |
| **Supabase** | `orders.restaurant_id` (text) + `orders.restaurant_uuid` (uuid, NOT NULL, FK → restaurants.id). RLS: anon SELECT kvar, authenticated per restaurang (get_current_restaurant_id). |
| **Lovable edge** | Hämtar från extern Supabase, filtrerar på `restaurant_id = 'Gislegrillen_01'`. Anon-nyckel. |
| **Railway** | En app, en `RESTAURANT_UUID` (Gislegrillen). |

Allt är byggt så att **en** restaurang fungerar stabilt. Multi-tenant är förberett i databasen (restaurants, restaurant_members, restaurant_uuid, RLS) men backend och Lovable är ännu “single-tenant”.

---

## Risker idag (noggrann genomgång)

### Låg risk
- **FK ON DELETE SET NULL:** Kolumnen är NOT NULL, så om någon försöker radera en restaurang som har ordrar kommer raderingen att **misslyckas** (Postgres kan inte sätta NULL). Ingen tyst dataförlust.
- **RLS:** Anon SELECT finns kvar → Lovable edge fortsätter fungera. Authenticated ser bara sin restaurang om de är kopplade i `restaurant_members`.
- **Backend:** Skickar alltid både `restaurant_id` (text) och `restaurant_uuid` när `RESTAURANT_UUID` är satt → Supabase insert kräver båda efter C1.

### Medel risk (vid flera restauranger)
- **En backend, flera restauranger:** Idag finns bara **en** `RESTAURANT_UUID` per deployment. För flera restauranger måste backend kunna bestämma **vilken** restaurang varje anrop gäller (t.ex. från Vapi `assistantId` eller annat tenant-fält) och antingen:
  - hämta (restaurant_id, restaurant_uuid) från databasen/config, eller
  - köra en backend per restaurang (varje med egen RESTAURANT_UUID).
- **Lovable:** Köksvyn filtrerar hårdkodat på `Gislegrillen_01`. För flera restauranger behöver antingen:
  - en dashboard per restaurang (olika “projekt”/filter), eller
  - att edge-funktionen tar emot restaurant_id/restaurant_uuid (t.ex. från inloggad användare eller val) och filtrerar på det.

### Åtgärd före fler restauranger
- **Backend:** Ersätt eller utöka `_get_restaurant_id_from_webhook(body)` så att restaurang identifieras från webhook (t.ex. `message.call.assistantId` eller eget fält). Mappa till `external_id` + uuid via `restaurants`-tabellen (eller env/config per tenant).
- **Lovable:** Anpassa så att köksvyn/edge använder rätt restaurang (parameter eller inloggning mot Gislegrillen-Supabase med `restaurant_members`).

---

## Checklista – “allt fungerar”

- [ ] Railway-test: `python3 test_order_railway.py` → 200, order_id i svar (✅ redan OK)
- [ ] Supabase: Senaste order har `restaurant_id` och `restaurant_uuid` ifyllda
- [ ] Lovable: Inloggad användare ser ordrar i NYA
- [ ] (Valfritt) Vapi: Ring, lägg order, synas i Supabase + Lovable

---

## Sammanfattning

- **Just nu:** Systemet är dubbelkollat från backend (test körts). Supabase-strukturen stödjer multi-tenant; backend och Lovable är fortfarande anpassade för en restaurang.
- **Risker:** Inga kända som bryter nuvarande en-restaurant-flöde. Vid övergång till flera restauranger krävs tydlig mappning webhook → restaurang i backend och anpassning av Lovable (vilken restaurang som visas).
- **Flera restauranger inom någon vecka:** Planera ändring i `_get_restaurant_id_from_webhook` + källa till `restaurant_uuid` (DB eller per-tenant config), samt hur varje restaurang ska se sina ordrar i Lovable (filter/parameter eller separat dashboard).
