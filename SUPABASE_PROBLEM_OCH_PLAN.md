# Supabase – nuvarande problem, framtida problem och plan

## Jag kan inte skriva till Supabase

Cursor har ingen åtkomst till Supabase Dashboard eller Supabase-chatt. Du måste själv antingen:
- skriva till Supabase (klistra in texten från **TILL_SUPABASE_VERIFIERA.md**), eller
- köra **supabase_verifiera_status.sql** i SQL Editor och tolka resultatet.

Nedan är en plan för vad som kan vara fel nu, vad som kan bli fel framöver, och hur du undersöker och åtgärdar.

---

## Nuvarande problem (möjliga)

| Problem | Hur du identifierar det | Åtgärd |
|--------|-------------------------|--------|
| **restaurant_uuid NULL på några rader** | Kör `supabase_verifiera_status.sql` fråga 3. orders_utan_uuid > 0. | Kör B4 (UPDATE ... SET restaurant_uuid = r.id FROM restaurants r WHERE ...). Sedan C1 om inte redan gjort. |
| **Kolumnen restaurant_uuid saknas eller är nullable** | Fråga 1 i verifieringsscriptet. | Be Supabase köra C1: ALTER COLUMN restaurant_uuid SET NOT NULL + ADD CONSTRAINT FK. |
| **FK orders_restaurant_uuid_fkey saknas** | Fråga 2 – tomt resultat. | Be Supabase lägga till FK mot public.restaurants(id) (ON DELETE SET NULL). |
| **Anon SELECT borttagen på orders** | Fråga 4 – ingen policy för anon. Eller Lovable visar inga ordrar trots inloggning. | Be Supabase: "Skapa policy för anon SELECT på public.orders med USING (true)." |
| **Dubbel/konfliktande RLS-policies** | Fråga 4 – många SELECT-policies, oklart vilka som gäller. | Be Supabase lista policies och ta bort duplikat (t.ex. behåll en anon SELECT, en authenticated SELECT). |

---

## Framtida problem (när ni har flera restauranger)

| Risk | Vad som händer | Förebyggande / plan |
|------|----------------|---------------------|
| **Backend skickar bara en RESTAURANT_UUID** | Alla ordrar hamnar på samma restaurang oavsett vilken Vapi-assistent som ringde. | Ändra backend: läs restaurang från webhook (t.ex. assistantId), slå upp i `restaurants` (eller env per tenant), skicka rätt restaurant_id + restaurant_uuid. |
| **Lovable visar bara Gislegrillen_01** | Andra restauranger ser inga ordrar i köksvyn. | Edge-funktion måste ta emot vilken restaurang (restaurant_id eller restaurant_uuid) och filtrera på det; eller separat dashboard/vy per restaurang. |
| **Radera restaurang med ordrar** | Idag: FK ON DELETE SET NULL men kolumn NOT NULL → radering av restaurang misslyckas. Det är säkert. | Om ni senare vill tillåta borttagning: antingen ON DELETE CASCADE (radera ordrar) eller tillåt NULL på restaurant_uuid och hantera “okänd restaurang” i appen. |
| **restaurant_members tom** | get_current_restaurant_id() returnerar NULL för inloggade → authenticated ser inga ordrar. | När ni använder inloggning mot denna Supabase: lägg användare i restaurant_members med rätt restaurant_id (uuid). |
| **Nya restauranger utan rad i restaurants** | Insert till orders med okänd restaurant_uuid → FK-fel. | Backend måste alltid använda uuid som finns i restaurants (och eventuellt skapa rad med external_id vid första order). |

---

## Smart plan – steg för steg

### Steg 1: Verifiera att allt gick igenom (nu)
1. Skriv till Supabase med texten i **TILL_SUPABASE_VERIFIERA.md**, **eller**
2. Kör **supabase_verifiera_status.sql** i SQL Editor och fyll i checklistan i TILL_SUPABASE_VERIFIERA.md.

### Steg 2: Åtgärda eventuella fel
- Om anon SELECT saknas → be Supabase lägga till.
- Om några rader har restaurant_uuid NULL → be Supabase köra B4, sedan kontrollera C1/FK igen.
- Om FK eller NOT NULL saknas → be Supabase köra C1-delen.

### Steg 3: Säkerställ att systemet fungerar
- Kör `python3 test_order_railway.py` → order skapas.
- Kolla i Supabase Table Editor att senaste order har både restaurant_id och restaurant_uuid.
- Logga in på Lovable och bekräfta att ordrar syns i NYA.

### Steg 4: Före fler restauranger (inom någon vecka)
- **Backend:** Implementera mappning webhook → restaurang (assistantId eller annat) → (restaurant_id, restaurant_uuid) från `restaurants` eller config.
- **Lovable:** Anpassa edge/köksvy så att restaurang kan väljas eller bestämmas (parameter / inloggning mot denna Supabase med restaurant_members).
- **Supabase:** Eventuellt lägg in nya restauranger i `restaurants` och användare i `restaurant_members` när nya tenants kommer.

---

## Sammanfattning

- **Verifiering:** Använd **TILL_SUPABASE_VERIFIERA.md** (text till Supabase) och/eller **supabase_verifiera_status.sql** (egen kontroll).
- **Nuvarande problem:** Listade i tabellen ovan med hur du identifierar och åtgärdar dem.
- **Framtida problem:** Backend måste kunna skilja restauranger; Lovable måste kunna filtrera per restaurang; restaurant_members måste användas om ni har inloggning mot denna Supabase.
