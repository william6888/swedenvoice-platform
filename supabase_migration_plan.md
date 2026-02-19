# Supabase migration: text restaurant_id → UUID (när ni är redo)

Kör **inte** detta förrän backend + Lovable är uppdaterade. Detta är en plan för senare.

## Fas A (redan gjort om du körde safe_phase1.sql)
- `restaurants` + `restaurant_members` skapade
- `restaurants.external_id = 'Gislegrillen_01'`
- `orders.restaurant_id` oförändrad (text), anon SELECT kvar

## Fas B – Backfill
- Finns redan: UUID för Gislegrillen i `restaurants` med `external_id = 'Gislegrillen_01'`

## Fas C – Migrera orders till UUID
1. Lägg till kolumn: `orders.restaurant_uuid uuid NULL`
2. Fyll: `UPDATE orders o SET restaurant_uuid = r.id FROM restaurants r WHERE o.restaurant_id = r.external_id`
3. Uppdatera backend (main.py) att skicka `restaurant_uuid` istället för text
4. Uppdatera Lovable edge-funktion att filtrera på UUID (eller läsa från mapping)
5. Verifiera att allt fungerar
6. Sätt `restaurant_uuid NOT NULL`, skapa FK till `restaurants(id)`, uppdatera RLS
7. (Valfritt) Ta bort eller behåll `orders.restaurant_id` (text) för legacy

## Varningar
- Ta inte bort anon SELECT på orders förrän edge-funktion använder authenticated eller service_role
- Skapa aldrig FK mellan `orders.restaurant_id` (text) och `restaurants.id` (uuid) – använd ny kolumn `restaurant_uuid`
