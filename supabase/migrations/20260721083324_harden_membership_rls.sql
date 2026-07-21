-- Memberships are provisioned by the trusted backend with service_role.
-- Allowing clients to INSERT/UPDATE their own row lets any authenticated user
-- choose an arbitrary restaurant_id/role and cross tenant boundaries.

begin;

drop policy if exists member_insert_own on public.restaurant_members;
drop policy if exists member_update_own on public.restaurant_members;
drop policy if exists member_delete_own on public.restaurant_members;

-- Kitchen clients only need to read their restaurant metadata. Tenant
-- administration remains a service_role/admin operation.
drop policy if exists restaurants_insert_member on public.restaurants;
drop policy if exists restaurants_update_member on public.restaurants;
drop policy if exists restaurants_delete_member on public.restaurants;

commit;
