-- Policies för public.orders (authenticated: UPDATE, INSERT, DELETE)
-- Kör i Supabase Dashboard → SQL Editor

CREATE POLICY "Allow update for authenticated" ON public.orders
  FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

CREATE POLICY "Allow insert for authenticated" ON public.orders
  FOR INSERT TO authenticated WITH CHECK (true);

CREATE POLICY "Allow delete for authenticated" ON public.orders
  FOR DELETE TO authenticated USING (true);
