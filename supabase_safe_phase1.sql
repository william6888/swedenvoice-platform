-- Fas 1: Icke-störande. Kör i Supabase SQL Editor.
-- Skapar restaurants + restaurant_members. Påverkar INTE orders.restaurant_id eller anon SELECT.

-- 1) Restaurants med external_id (text) — matchar nuvarande 'Gislegrillen_01'
CREATE TABLE IF NOT EXISTS public.restaurants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id text UNIQUE,
  name text,
  api_key text UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- 2) Restaurant_members för framtida auth-kopplingar
CREATE TABLE IF NOT EXISTS public.restaurant_members (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
  restaurant_id uuid REFERENCES public.restaurants(id) ON DELETE CASCADE,
  role text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (auth_user_id)
);

-- 3) Index på orders.restaurant_id (text)
CREATE INDEX IF NOT EXISTS idx_orders_restaurantid_text ON public.orders (restaurant_id);

-- 4) Gislegrillen-rad (stör inte orders)
INSERT INTO public.restaurants (external_id, name)
VALUES ('Gislegrillen_01', 'Gislegrillen')
ON CONFLICT (external_id) DO NOTHING;
