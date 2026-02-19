# Multi-tenancy – säker plan (allt fungerar, ingen driftstopp)

Målet: Riktig multi-tenant-struktur med UUID, RLS och ren kod – **utan att Lovable eller nuvarande flöde bryts**.

---

## Princip

- **orders.restaurant_id** (text, t.ex. `Gislegrillen_01`) behålls tills vidare → Lovable edge-funktionen behöver inte ändras.
- **orders.restaurant_uuid** (uuid) läggs till och används för RLS och framtida fler restauranger.
- **Anon SELECT** på orders behålls så att edge-funktionen fortsatt kan läsa med anon.
- **Authenticated** får egna RLS-policies (per restaurang) när `get_current_restaurant_id()` finns.

---

## Vad som redan är gjort

- [x] **Fas 1 (Supabase):** `restaurants`, `restaurant_members`, rad för `Gislegrillen_01`, index på `orders.restaurant_id`.
- [x] **Backend:** Stöd för `RESTAURANT_UUID` – när den är satt skickas både `restaurant_id` (text) och `restaurant_uuid` vid insert. Ingen breaking change.

---

## Körordning (så att inget går sönder)

### 1. Supabase – be om funktion + migrationsplan

Skriv till Supabase:

- **"create-func"** – så skapar de `get_current_restaurant_id()` (används inte förrän du lägger till RLS för authenticated).
- **"migrationsplan"** – så får du färdigt SQL för Fas B–C.

### 2. Supabase – kör Fas B–C (när du fått scriptet)

Typiskt innehåll:

1. Lägg till kolumn: `orders.restaurant_uuid uuid NULL`.
2. Backfill:  
   `UPDATE orders o SET restaurant_uuid = r.id FROM restaurants r WHERE r.external_id = o.restaurant_id;`
3. Skapa **inte** FK ännu (eller enligt Supabase script).
4. **Behåll anon SELECT** på orders – ta inte bort den.
5. Lägg till RLS-policies för **authenticated** som använder `get_current_restaurant_id()` (SELECT/INSERT/UPDATE/DELETE för egen restaurang).

Efter detta: nya och gamla ordrar har både `restaurant_id` (text) och `restaurant_uuid`. Lovable kan fortsätta filtrera på `restaurant_id = 'Gislegrillen_01'`.

### 3. Hämta Gislegrillens UUID

I Supabase SQL Editor:

```sql
SELECT id FROM public.restaurants WHERE external_id = 'Gislegrillen_01';
```

Kopiera UUID (t.ex. `a1b2c3d4-...`).

### 4. Backend (Railway + lokalt)

- **Railway:** Variables → lägg till `RESTAURANT_UUID` = den UUID du kopierade.
- **Lokalt:** I `.env` lägg till `RESTAURANT_UUID=<samma-uuid>`.
- Deploya / starta om servern.

Därefter skickar backend både `restaurant_id` och `restaurant_uuid` vid varje insert. Lovable och övriga system påverkas inte.

### 5. (Valfritt) Lovable

- Du behöver **inte** ändra edge-funktionen: den kan fortsätta läsa med anon och filtrera på `restaurant_id = 'Gislegrillen_01'`.
- Om du senare vill att köksvyn bara ska visa ordrar för inloggad användares restaurang (via `restaurant_members` i **Gislegrillen-Supabase**), måste användare finnas i den Supabase Auth + `restaurant_members`. Idag använder Lovable egen auth (Lovable Cloud), så den här varianten är framtidsarbete.

### 6. Verifiering

- Ring/testa en order → kolla i Supabase att raden har både `restaurant_id` och `restaurant_uuid`.
- Öppna Lovable köksvy (inloggad) → ordrar ska fortfarande visas i NYA.

---

## Sammanfattning

| Del | Ändras? | Risk |
|-----|--------|------|
| orders.restaurant_id (text) | Behålls | Ingen |
| orders.restaurant_uuid | Ny kolumn + backfill | Ingen om du inte tar bort/ändrar anon SELECT |
| Backend | Skickar restaurant_uuid när RESTAURANT_UUID är satt | Ingen |
| Lovable edge-fn | Ingen ändring krävs | Ingen |
| RLS anon SELECT | Behålls | Ingen |
| RLS authenticated | Nya policies med get_current_restaurant_id() | Säker – anon påverkas inte |

Resultat: Multi-tenant-struktur med ren separation per restaurang, samtidigt som nuvarande system och kod fortsätter fungera.
