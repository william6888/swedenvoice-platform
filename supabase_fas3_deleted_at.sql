-- Fas 3: Soft delete på restaurants. Kör i Supabase SQL Editor efter Fas 2.
-- Alla "aktiva"-queries ska filtrera på deleted_at IS NULL.
-- CASCADE: restaurant_secrets och restaurant_members har redan ON DELETE CASCADE. Orders har INTE CASCADE.

ALTER TABLE public.restaurants
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz NULL;

COMMENT ON COLUMN public.restaurants.deleted_at IS 'Soft delete: NULL = aktiv; sätt till now() för att inaktivera. Aktiva-tenant-set och config använder WHERE deleted_at IS NULL.';

-- Index för snabb filtrering vid refresh av aktiva tenants
CREATE INDEX IF NOT EXISTS idx_restaurants_deleted_at ON public.restaurants (deleted_at) WHERE deleted_at IS NULL;
