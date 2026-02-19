-- Kör i Supabase SQL Editor för att verifiera att migrationen (B+C1+RLS) gick igenom.
-- Projekt: zgllqocecavcgctbduip (Gislegrillen)

-- 1) Finns kolumnen restaurant_uuid och är den NOT NULL?
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'orders'
  AND column_name IN ('restaurant_id', 'restaurant_uuid');

-- 2) Finns FK orders_restaurant_uuid_fkey?
SELECT conname, conrelid::regclass, confrelid::regclass
FROM pg_constraint
WHERE conrelid = 'public.orders'::regclass AND contype = 'f';

-- 3) Antal ordrar med/utan restaurant_uuid (ska vara 0 utan)
SELECT COUNT(*) FILTER (WHERE restaurant_uuid IS NULL) AS orders_utan_uuid,
       COUNT(*) FILTER (WHERE restaurant_uuid IS NOT NULL) AS orders_med_uuid,
       COUNT(*) AS totalt
FROM public.orders;

-- 4) RLS-policies på orders (förväntat: anon SELECT + authenticated SELECT/INSERT/UPDATE/DELETE)
SELECT pol.polname,
       CASE pol.polcmd WHEN 'r' THEN 'SELECT' WHEN 'a' THEN 'INSERT' WHEN 'w' THEN 'UPDATE' WHEN 'd' THEN 'DELETE' ELSE pol.polcmd::text END AS command,
       (SELECT string_agg(rolname, ', ') FROM pg_roles WHERE oid = ANY(pol.polroles)) AS roles
FROM pg_policy pol
JOIN pg_class c ON c.oid = pol.polrelid
WHERE c.relname = 'orders' AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public');

-- 5) Senaste ordrar – har både restaurant_id och restaurant_uuid
SELECT id, restaurant_id, restaurant_uuid, status, created_at
FROM public.orders
ORDER BY created_at DESC
LIMIT 3;
