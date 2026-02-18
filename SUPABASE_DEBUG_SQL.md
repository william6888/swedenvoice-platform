# Supabase felsökning – SQL att köra i SQL Editor

Klistra in och kör i **Supabase Dashboard → SQL Editor** (som projektägare).

## 1. Kontrollera om rader finns (oavsett RLS)
```sql
SELECT * FROM public.orders ORDER BY created_at DESC LIMIT 10;
```
- **Ser du rader** → problemet är troligen SELECT-policies i Table Editor.
- **Ser du inga rader** → INSERT når inte databasen eller skrivs till fel schema/projekt.

---

## 2. Testa INSERT manuellt (snabbtest)
```sql
INSERT INTO public.orders (restaurant_id, customer_name, customer_phone, items, total_price, status, raw_transcript)
VALUES ('test-rest', 'Test', '0700000000', '[]'::jsonb, 0.00, 'NYA', 'manual_test')
RETURNING *;
```
Kör sedan SELECT från steg 1 igen. Om manuell insert syns men backend-insert inte gör det → problemet är i klienten/headers.

---

## 3. Visa RLS-policies på orders
```sql
SELECT pol.polname, pol.polcmd, pg_get_expr(pol.polqual, pol.polrelid) AS using_expr
FROM pg_policy pol
JOIN pg_class cls ON pol.polrelid = cls.oid
WHERE cls.relname = 'orders';
```

---

## 4. Kontrollera triggers (kan ta bort/flytta rader)
```sql
SELECT tgname FROM pg_trigger WHERE tgrelid = 'public.orders'::regclass;
```
Om triggers finns – problemet kan vara där.
