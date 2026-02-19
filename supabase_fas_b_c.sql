-- Fas B–C: restaurant_uuid på orders (Supabase levererade scriptet)
-- Kör stegvis. Behåll anon SELECT tills edge/backend är uppdaterade.

-- ========== B1) Lägg till kolumn ==========
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS restaurant_uuid uuid;

-- ========== B2) Backfill från restaurants via external_id ==========
UPDATE public.orders o
SET restaurant_uuid = r.id
FROM public.restaurants r
WHERE o.restaurant_id = r.external_id AND o.restaurant_uuid IS DISTINCT FROM r.id;

-- ========== B3) Verifiering (kör som SELECT) ==========
-- SELECT COUNT(*) AS orders_without_uuid FROM public.orders WHERE restaurant_uuid IS NULL;
-- SELECT COUNT(*) AS orders_with_uuid FROM public.orders WHERE restaurant_uuid IS NOT NULL;

-- ========== B4) Efter att backend skriver restaurant_uuid – synka ev. nya rader ==========
-- UPDATE public.orders o SET restaurant_uuid = r.id FROM public.restaurants r
-- WHERE o.restaurant_id = r.external_id AND o.restaurant_uuid IS NULL;

-- ========== C1) När allt verifierat: NOT NULL + FK ==========
-- ALTER TABLE public.orders ALTER COLUMN restaurant_uuid SET NOT NULL;
-- ALTER TABLE public.orders ADD CONSTRAINT orders_restaurant_uuid_fkey
--   FOREIGN KEY (restaurant_uuid) REFERENCES public.restaurants (id) ON DELETE SET NULL;

-- ========== RLS: authenticated (behåll anon SELECT) ==========
-- ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY orders_select_authenticated ON public.orders
--   FOR SELECT TO authenticated USING (restaurant_uuid = public.get_current_restaurant_id());
-- Anon SELECT ska finnas kvar tills ni bytt edge/backend:
-- CREATE POLICY orders_select_anon ON public.orders FOR SELECT TO anon USING (true);
-- (eller USING (restaurant_id = 'Gislegrillen_01') om ni vill begränsa)
