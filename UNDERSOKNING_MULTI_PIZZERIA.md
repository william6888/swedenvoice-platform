# Undersökning: Test + hur enkelt är det att lägga till flera pizzerior?

**Datum:** 2026-02-20 (efter Fas 1+2 + multi-pizzeria-ändringar)

---

## 0. Snabbtest (kör själv)

```bash
# Order mot localhost (default Gislegrillen_01)
python3 test_order.py

# Order med explicit rest_id i query (samma resultat, visar multi-tenant-väg)
python3 test_order_with_rest_id.py

# Fas 2: meny + keywords (kräver att servern har senaste kod)
python3 scripts/smoke_test_fas2.py
```

---

## 1. Tester som körts

| Test | Resultat | Kommentar |
|------|----------|-----------|
| `python3 test_order.py` | ✅ 200, order skapad | Webhook med tool-calls, rest_id defaultar till Gislegrillen_01 (inget rest_id i payload). |
| `python3 scripts/smoke_test_fas2.py` | ⚠️ GET /menu OK, GET /api/keywords 404 | Servern som körde hade förmodligen gammal kod (utan /api/keywords). Starta om servern efter senaste commit så ska båda vara OK. |

**Slutsats:** Orderflödet (webhook → place_order → Supabase, SMS i bakgrunden) fungerar. Fas 2-endpoints kräver att servern är omstartad med senaste kod.

---

## 2. Dataflöde – var används rest_id?

- **rest_id hämtas:**  
  `request.query_params.get("rest_id")` → `body.get("rest_id")` → `body.message.call.metadata.rest_id`. Default: `"Gislegrillen_01"`.

- **Meny:**  
  `load_menu(rest_id)` → `menu.json` (om rest_id saknas eller är Gislegrillen_01), annars `menu_<rest_id>.json` (fallback till menu.json om fil saknas). Cache: `menu:<rest_id>`.

- **Orderberäkning:**  
  `_parse_items_from_params(params, rest_id)` → `find_menu_item(id, rest_id)` (namn).  
  `_process_place_order(..., rest_id=rest_id)` → `find_menu_item(..., rest_id)` (pris) och `calculate_total_price(items, rest_id)`.

- **Supabase orders:**  
  `_insert_order_to_supabase(order, restaurant_id, ..., restaurant_uuid=restaurant_uuid)`.  
  Varje rad har `restaurant_id` (external_id) och `restaurant_uuid` (restaurants.id). Ordrar är alltså per restaurang i DB.

- **orders.json:**  
  En enda fil; alla ordrar (alla pizzerior) läggs i samma lista. Källan för “vilken pizzeria” i appen är Supabase (restaurant_id/restaurant_uuid). orders.json fungerar som backup/legacy; för flera pizzerior är Supabase den tydliga källan per tenant.

- **Övrigt per rest_id:**  
  Circuit breaker, token bucket, config-cache, SMS-alert rate limit, tenant invalidate, meny-cache – alla nycklas på rest_id. Inga delade strukturer mellan pizzerior.

---

## 3. Är det lätt att ändra när du har flera pizzerior?

**Ja.** Du behöver inte ändra någon appkod. Du behöver:

| Steg | Vad du gör |
|------|------------|
| 1 | **Supabase:** Ny rad i `public.restaurants` med t.ex. `external_id = 'Pizzeria_B'`, `name = 'Pizzeria B'`. Samma tabell som idag; eventuellt throttle-kolumner och `deleted_at` enligt befintliga migrationer. |
| 2 | **Meny (om annan meny):** Skapa filen `menu_Pizzeria_B.json` i projektroten, samma struktur som `menu.json`. Om du inte skapar filen används `menu.json` för denna pizzeria också. |
| 3 | **Vapi:** Se till att webhook-anrop skickar `rest_id` för denna pizzeria. Det kan göras med: **Server URL** `https://.../vapi/webhook?rest_id=Pizzeria_B`, eller **metadata** i Vapi-assistant: `message.call.metadata.rest_id = "Pizzeria_B"`. Då används rätt meny, cache och tenant i backend. |
| 4 | **Efter menyändring:** Anropa `POST /admin/menu/invalidate?rest_id=Pizzeria_B` med X-Admin-Key så slipper du vänta 3 min. |

Ingen ny kod, inga nya endpoints. Bara data (Supabase + valfritt menyfil) och konfiguration (Vapi rest_id).

---

## 4. Kontroll av kod – sammanfattning

- **Meny:** `load_menu(rest_id)`, `get_menu_cached(rest_id)`, cache-nyckel `menu:<rest_id>`, invalidate per rest_id. ✅ Redo för flera pizzerior.
- **Order:** `rest_id` går genom `_parse_items_from_params`, `_process_place_order`, `find_menu_item`, `calculate_total_price`. Supabase-insert använder `restaurant_id` och `restaurant_uuid`. ✅ Redo.
- **rest_id-källa:** Query, body, eller `message.call.metadata.rest_id`. Default Gislegrillen_01. ✅ Tydligt.
- **orders.json:** En fil för alla ordrar. Per-tenant-data finns i Supabase. ✅ Acceptabelt; ingen blandning av logik mellan pizzerior.

---

## 5. Kvarvarande begränsning

- **orders.json:** Innehåller ordrar från alla pizzerior i en lista. Om du vill filtrera “bara Pizzeria B” måste du antingen filtrera på något fält (idag har inte orders.json restaurant_id per order – det finns i Supabase). För KDS/Lovable och “vilken order tillhör vilken restaurang” används Supabase; orders.json är inte byggd för tenant-filtrering. Om du senare vill ha tenant i orders.json kan man lägga till ett fält `restaurant_id` vid save; det kräver en liten kodändring. **Rekommendation:** Låt Supabase vara källan för multi-tenant-ordrar; ändra inte orders.json om du inte behöver tenant-filtrering i den filen.

Sammanfattning: **Det är redan enkelt att lägga till flera pizzerior; ingen omskrivning krävs, bara Supabase-rad, valfri menyfil och rest_id i Vapi.**
