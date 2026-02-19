# Supabase Advisor – vad du ska göra (utan att bryta Lovable)

Viktigt: **Ändra inte** anon SELECT på `orders` (USING true) förrän Lovable använder inloggning mot Supabase. Annars slutar ordrar att visas i köksvyn.

---

## Gör nu (säkert)

### 1. Funktion search_path (säkrare, påverkar inte flödet)
**Skriv till Supabase:**  
"Fixa 'Function Search Path Mutable' för get_current_restaurant_id: sätt explicit search_path i funktionen, t.ex.  
CREATE OR REPLACE FUNCTION public.get_current_restaurant_id() RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$ [nuvarande body] $$;  
Behåll samma logik, bara lägg till SET search_path = public."

### 2. Index på foreign keys (prestanda, påverkar inte åtkomst)
**Skriv till Supabase:**  
"Skapa index på foreign key-kolumner som Advisor flaggar:  
- public.orders: index på restaurant_uuid (om det saknas).  
- public.restaurant_members: index på auth_user_id och restaurant_id om de saknas.  
Kör bara CREATE INDEX om indexet inte redan finns."

### 3. RLS på restaurants och restaurant_members (säkerhet)
**Du kan aktivera RLS** på dessa tabeller. Backend (Railway) läser inte från dem vid insert – den använder bara RESTAURANT_UUID från env.  
**Skriv till Supabase:**  
"Aktivera RLS på public.restaurants och public.restaurant_members. Skapa policies så att authenticated kan läsa rader (t.ex. alla eller via get_current_restaurant_id). Service_role ska fortfarande bypassa RLS. Backend använder service_role och skickar inte läs från dessa tabeller – bara insert till orders."

---

## Gör INTE nu (annars bryter Lovable)

### "RLS Policy Always True" på public.orders
Advisor varnar för policies med USING (true). **Vi har medvetet** en anon SELECT med USING (true) så att Lovables edge-funktion kan läsa ordrar med anon-nyckel.  
**Om du tar bort eller begränsar den** (t.ex. bara authenticated) kommer Lovable att få tomt svar och köksvyn visar inga ordrar.  
**Åtgärd:** Låt anon SELECT på orders vara tills du har bytt till Auth i Lovable. När Lovable använder inloggad användare och edge-funktionen skickar JWT kan du strama åt eller ta bort anon SELECT.

---

## Känsliga kolumner (restaurants)

Om **api_key** eller liknande i `restaurants` flaggas som känslig: antingen låt den vara NULL (som nu) eller skapa en policy så att endast service_role/authenticated med rätt roll kan läsa den. **Ta inte bort** anon SELECT på **orders** för att lösa detta – det är en annan tabell.

---

## Oanvänd index

Om Advisor säger "Unused Index" på orders: be Supabase lista vilket index det gäller (SELECT från pg_stat_user_indexes eller liknande). Ta bort **bara** om det verkligen aldrig används och du har kört en tid i produktion. Nya index kan användas när trafiken ökar.

---

## Sammanfattning – vad du svarar Supabase

"Kör 1) search_path-fix för get_current_restaurant_id, 2) index på FK för orders och restaurant_members om de saknas, 3) aktivera RLS på restaurants och restaurant_members med policies för authenticated. **Ändra inte** anon SELECT-policy på public.orders (USING true) – den behövs för vår edge-funktion tills vi byter till Auth. När det är klart, lista vilket index som flaggas som 'Unused' på orders så vi kan utvärdera det."  

Om Supabase frågar om "RLS Policy Always True" på orders:  
"Låt den policy som ger anon SELECT med USING (true) vara. Vi tar bort den när vår klient använder Auth istället för anon."
