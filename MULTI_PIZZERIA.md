# Flera pizzerior – ingen blandning

Systemet är byggt så att **varje pizzeria (tenant) är helt isolerad**. Inget blandas ihop.

## Hur det fungerar

- **rest_id** = identifierare för en pizzeria (t.ex. `Gislegrillen_01`, `Pizzeria_B`). Kommer från Vapi (query `?rest_id=...` eller body) eller från Supabase `restaurants.external_id`.

- **En worker** (`Procfile`: `--workers 1`)  
  All trafik går genom samma process. När du anropar t.ex. `POST /admin/menu/invalidate?rest_id=Pizzeria_B` rensas bara den pizzerians meny-cache – inga andra påverkas. Hade vi flera workers skulle varje process ha egen cache; då gäller invalidate bara i den process som fick anropet.

- **Meny per pizzeria**  
  - **Gislegrillen_01** (eller om rest_id saknas): använder `menu.json`.  
  - **Annan rest_id** (t.ex. Pizzeria_B): systemet letar efter `menu_Pizzeria_B.json`. Finns filen används den; annars fallback till `menu.json`.  
  Så du behöver bara lägga till en fil, t.ex. `menu_Pizzeria_B.json`, när du lägger till en ny pizzeria. Samma struktur som `menu.json` (pizzas, kebabs, …).

- **Cache är per rest_id**  
  Cachen nycklas som `menu:Gislegrillen_01`, `menu:Pizzeria_B` osv. GET /menu, GET /api/keywords, orderberäkning (priser, namn) använder alltid rätt rest_id genom hela kedjan, så Pizzeria A:s meny och ordrar blandas aldrig med Pizzeria B:s.

- **Övrigt per rest_id**  
  Circuit breaker, token bucket, config-cache, SMS-alerts och tenant-invalidate är också per rest_id. En pizzeria påverkar inte den andra.

## När du lägger till en ny pizzeria

1. Lägg till tenant i Supabase (`restaurants` med t.ex. `external_id = Pizzeria_B`).
2. (Valfritt) Skapa `menu_Pizzeria_B.json` om menyn skiljer sig; annars används `menu.json` för alla.
3. I Vapi: skicka `rest_id` (query eller body) så att anrop kopplas till rätt pizzeria.
4. Efter ändring av en pizzerias meny: anropa `POST /admin/menu/invalidate?rest_id=Pizzeria_B` (med X-Admin-Key) så slipper du vänta 3 min.

## Sanitering av keywords

Keyword-sanitering (GET /api/keywords) är samma för alla pizzerior: bokstaver (inkl. åäö), siffror, mellanslag, bindestreck, apostrof, parenteser; max 50 tecken. Det påverkar bara hur namnen skickas till t.ex. Speechmatics – varje pizzeria får fortfarande sina egna keywords från sin egen meny (via `?rest_id=...`). Inget blandas.
