# Fas 3: Livscykel (soft delete)

## Gör

1. **Kör SQL-migration i Supabase** (en gång):  
   `supabase_fas3_deleted_at.sql` – lägger till `deleted_at` på `restaurants` och index.

2. **Aktiva tenants**  
   Backend uppdaterar aktiva-tenant-set var 1:e minut med `WHERE deleted_at IS NULL`.  
   Config-lookup och restaurant-lookup returnerar bara rader där `deleted_at IS NULL`.

3. **Soft delete (radera tenant)**  
   - **Alternativ A:** Anropa `POST /admin/tenants/{rest_id}/soft-delete` med `X-Admin-Key: <ADMIN_SECRET>`.  
     Det gör: (1) invalidate (Instant Kill), (2) sätter `deleted_at = now()` i DB.  
   - **Alternativ B:** Anropa först `POST /admin/tenants/{rest_id}/invalidate`, sätt sedan `deleted_at` i Supabase (Dashboard eller SQL) för den restaurangen.

4. **CASCADE**  
   `restaurant_secrets` och `restaurant_members` har redan `ON DELETE CASCADE` mot `restaurants`.  
   **Orders** har **inte** CASCADE – ordrar behålls vid soft delete.

5. **Hard delete (valfritt, senare)**  
   För restaurang med `deleted_at` satt och efter laglig kvarhållning: script eller admin-endpoint som raderar orders för den `restaurant_uuid`, därefter secrets/members, till sist restaurants-raden. Manuellt eller schemalagt.

## Bakåtkompatibilitet

Om migrationen inte är körd använder backend fallback utan `deleted_at`-filter (alla rader anses aktiva). Du ser då varningen:  
`Fas 3: kör supabase_fas3_deleted_at.sql för soft delete (deleted_at saknas)`.
