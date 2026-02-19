# Fas 1–3: Felsökning och kända begränsningar

## Åtgärdade problem (denna genomgång)

- **Fas 1:** Vid invalidate/soft-delete rensas nu även circuit breaker och token bucket för den tenant (minskar minnesanvändning och undviker kvarstående state för borttagna tenants).
- **Fas 2:** Alla fallback-queries i `_fetch_restaurant_config_from_db` använder nu `deleted_at IS NULL`, så vi returnerar inte config för soft-deleted restauranger även vid nätverksfallback.
- **Fas 3:** Soft-delete utan Supabase returnerar tydligt meddelande att endast caches rensats och att `deleted_at` måste sättas manuellt i DB.

## Kända begränsningar

### `/place_order` med direktformat (utan Vapi)

- **Beteende:** Om du skickar `POST /place_order` med enbart `{"items": [...], "special_requests": "..."}` (direktformat, ingen `message`/tool-calls) går anropet **inte** genom Fas 1–3: ingen rest_id, ingen circuit breaker, ingen token bucket, ingen tenant-validering.
- **Konsekvens:** Använd endast för tillförlitliga källor (t.ex. intern app eller test). För Vapi och multi-tenant ska anrop gå via webhook eller via place_order med Vapi-format (där rest_id finns).

### Per-tenant Vonage/Pushover (Fas 2)

- **Nuvarande:** Pushover och Vonage använder globala env-variabler (`PUSHOVER_*`, `VONAGE_*`). `tenant_secrets` från `restaurant_secrets` cachar vi men använder inte än för utskick.
- **Framtid:** För per-tenant SMS/Pushover behöver `send_pushover_notification` och `send_sms_order_confirmation` ta emot (eller slå upp) tenant-config och använda nycklar därifrån när de finns.

### Flera workers (Railway/Gunicorn)

- **Aktiva-set, caches, circuit breaker, token bucket** är i minnet per process. Vid flera workers delas de inte: invalidate/soft-delete på en worker påverkar inte de andra förrän nästa DB-refresh (1 min).
- **Lösning:** Kör en worker om Instant Kill ska vara processövergripande, eller acceptera upp till 1 minuts fördröjning på andra workers.

## Kontrollista vid fel

1. **"Restaurangen kunde inte hittas"** – Kontrollera att restaurangen finns i Supabase med rätt `external_id` och att `deleted_at` är NULL.
2. **Circuit breaker öppen** – Kolla Pushover-alerts; vänta 60 s eller anropa invalidate för att rensa state (eller starta om servern).
3. **Soft-delete verkar inte** – Körde du `supabase_fas3_deleted_at.sql`? Har Railway/Supabase rätt env (SUPABASE_URL/SUPABASE_KEY)?
