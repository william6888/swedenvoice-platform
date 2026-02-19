# Fas 2: Engine (dynamisk onboarding)

## Vad som är implementerat

- **restaurant_secrets:** Tabell för krypterade tenant-nycklar (SQL i `supabase_fas2_restaurant_secrets.sql`).
- **Throttle per restaurang:** Kolumner `throttle_bucket_size`, `throttle_refill_per_sec` på `restaurants` (samma SQL).
- **Kryptering:** Fernet med `ENCRYPTION_SECRET`; hjälpfunktionerna `_decrypt_tenant_config` / `_encrypt_tenant_config`.
- **Config-cache:** Vid cache-miss hämtas throttle från DB och eventuellt dekrypterad config från `restaurant_secrets`; cachen innehåller `throttle_bucket_size`, `throttle_refill_per_sec` (och vid behov `tenant_secrets`).
- **Token bucket:** Använder per-tenant-parametrar från config-cache (default 20 och 0.1/s om inget satt i DB).

## Steg för dig

1. **Supabase:** Kör `supabase_fas2_restaurant_secrets.sql` i SQL Editor (skapar tabell + throttle-kolumner).
2. **Railway/lokal:** Sätt `ENCRYPTION_SECRET` (minst 32 tecken) om du ska använda `restaurant_secrets`. Utan den fungerar allt som tidigare med globala env och default throttle.
3. **Valfritt:** Sätt `throttle_bucket_size` / `throttle_refill_per_sec` per restaurang i `restaurants`; annars används default 20 och 0.1.

## Fas 3 (nästa)

Soft delete (`deleted_at` på restaurants), CASCADE på restaurant_secrets, raderingsflöde med invalidate.
