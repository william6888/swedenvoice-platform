-- Fas 2: restaurant_secrets (krypterade tenant-nycklar) + throttle-kolumner på restaurants.
-- Kör i Supabase SQL Editor. Kräver att public.restaurants redan finns.

-- 1) Throttle-parametrar per restaurang (defaults används i app om NULL)
ALTER TABLE public.restaurants
  ADD COLUMN IF NOT EXISTS throttle_bucket_size int,
  ADD COLUMN IF NOT EXISTS throttle_refill_per_sec numeric(10,4);

COMMENT ON COLUMN public.restaurants.throttle_bucket_size IS 'Token bucket size; default 20 i app om NULL';
COMMENT ON COLUMN public.restaurants.throttle_refill_per_sec IS 'Refill per sekund; default 0.1 i app om NULL';

-- 2) Tabell för krypterade tenant-nycklar (Vonage, Pushover, etc.)
CREATE TABLE IF NOT EXISTS public.restaurant_secrets (
  restaurant_uuid uuid PRIMARY KEY REFERENCES public.restaurants(id) ON DELETE CASCADE,
  encrypted_config text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.restaurant_secrets IS 'Krypterad JSON med tenant-nycklar (Vonage, Pushover). Endast service_role läser.';

-- 3) RLS: aktiverad utan policy för anon/authenticated → de får ingen åtkomst.
-- service_role bypassar RLS i Supabase och behåller full åtkomst; backend använder service_role.
ALTER TABLE public.restaurant_secrets ENABLE ROW LEVEL SECURITY;
