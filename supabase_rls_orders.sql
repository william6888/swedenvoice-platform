-- RLS (Row Level Security) för public.orders
-- Kör i Supabase SQL Editor: https://supabase.com/dashboard/project/_/sql
--
-- Viktigt: Backend (FastAPI) ska använda service_role-nyckeln – den bypassar RLS.
-- Lovable-dashboard använder anon/authenticated – behöver explicit policy för SELECT.

-- 1. Aktivera RLS
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;

-- 2. Policy: Låt anon läsa alla orders (för KDS-dashboard)
-- Om du senare vill begränsa per restaurant_id, ändra USING till:
--   USING (restaurant_id = current_setting('app.restaurant_id', true))
CREATE POLICY "orders_select_anon"
  ON public.orders
  FOR SELECT
  TO anon
  USING (true);

-- 3. Policy: Låt authenticated läsa alla orders
CREATE POLICY "orders_select_authenticated"
  ON public.orders
  FOR SELECT
  TO authenticated
  USING (true);

-- 4. Policy: Tillåt service_role INSERT/UPDATE/DELETE (service_role bypassar RLS ändå,
--    men det skadar inte att ha explicita policies för framtida användning)
-- OBS: service_role bypassar RLS automatiskt – backend ska alltid använda service_role!
