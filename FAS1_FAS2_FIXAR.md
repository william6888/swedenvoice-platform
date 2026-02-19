# Fas 1 & Fas 2 – genomförda fixar (autonom granskning)

## Identifierade och åtgärdade problem

### 1. Circuit breaker: ingen andra alert vid återöppning
- **Problem:** När breakern stängde efter 60 s återställdes inte `alert_sent`. Vid nästa öppning (5 nya fel) skickades därför ingen notis.
- **Åtgärd:** I `_circuit_breaker_allow` sätts `alert_sent = False` när breakern anses stängd (nu >= open_until_ts), så att nästa öppning ger en ny Pushover-alert.

### 2. Instant Kill: UUID togs inte bort från aktiva-set
- **Problem:** Planen kräver att invalidate "omedelbart tar bort rest_id/restaurant_uuid från aktiva-tenant-set". Endast cache rensades; UUID fanns kvar i `_ACTIVE_TENANT_UUIDS` tills nästa refresh (upp till 60 s).
- **Åtgärd:** I `_invalidate_tenant_caches` hämtas `restaurant_uuid` från config-cachen (innan den rensas) och tas bort från `_ACTIVE_TENANT_UUIDS` med `discard()`. Därefter rensas cache som tidigare.

### 3. Token bucket: ogiltiga parametrar kunde låsa ute
- **Problem:** Om DB hade `throttle_bucket_size = 0` eller `throttle_refill_per_sec <= 0` (eller icke-numeriska värden) kunde tenant i praktiken bli permanent blockerad eller ge fel.
- **Åtgärd:** I `_token_bucket_allow` klämps `bucket_size` till minst 1 och `refill_per_sec` till minst 0.01, med try/except för icke-numeriska värden (fallback till default).

### 4. Dokumentation för Fas 3
- **Åtgärd:** Kommentar i `_refresh_active_tenant_set` om att Fas 3 ska filtrera på `deleted_at IS NULL` när kolumnen finns.

---

Inga andra fel hittades i Fas 1/Fas 2-flödena (aktiva-set, config-cache, circuit breaker, token bucket, admin invalidate, kryptering, throttle från DB). Tester körda: token bucket clamp, circuit breaker alert-reset, invalidate med UUID-borttagning.
