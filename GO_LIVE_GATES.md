# Go-Live Gates – Autonomous Pizza Platform

Inget av detta system får säljas externt eller släppas live för en pizzeria
förrän samtliga gates nedan är gröna. Listan är operativ – om en gate misslyckas
ska launchen pausas, oavsett tidsplan.

## Innan första pilot

### 1. Migrationer körda
- [ ] `supabase_phase1_order_integrity.sql` är applicerad i pilot-projektets Supabase.
- [ ] `idempotency_records`, `order_events`, `incidents`, `ops_actions`,
      `sms_jobs`, `tenant_health` är synliga och RLS aktiverat.
- [ ] `orders` har de nya kolumnerna (`vapi_call_id`, `idempotency_key`,
      `payload_hash`, `needs_human_review`, `validation_version`, `source`).

### 2. Konfiguration
- [ ] `SUPABASE_KEY` är `service_role` (inte `anon`) på Railway.
- [ ] `RESTAURANT_UUID` är satt eller `restaurants.external_id` är synkad.
- [ ] `ADMIN_SECRET` är satt och delad med dig (inte i kod).
- [ ] `WEBHOOK_SHARED_SECRET` är satt och Vapi skickar header
      `X-Webhook-Secret` eller `Authorization: Bearer ...` som matchar.
- [ ] `DRAFT_SIGNING_SECRET` är satt (eller fall-back till `ENCRYPTION_SECRET`).
- [ ] `ORDER_REQUIRE_DB_COMMIT=true` (default).
- [ ] `DASHBOARD_FROM_DB=true` (default).
- [ ] Vapi pekar på `/vapi/webhook` (eller `/place_order` om det är dit tool URL går).

### 3. Automatiska tester
- [ ] `pytest -q` är grönt lokalt och i CI.
- [ ] Specifika kontroller:
  - [ ] Samma payload 5x ger en order (`test_five_retries_create_one_order`).
  - [ ] Två parallella requests ger en order
        (`test_concurrent_same_payload_creates_one_order`).
  - [ ] Supabase-fel → `success:false`, ingen order
        (`test_supabase_failure_returns_failure_and_no_order`).
  - [ ] `id/name` mismatch blockeras
        (`test_id_name_mismatch_is_blocked`).
  - [ ] Ogiltig orderstatus avvisas
        (`test_update_status_request_rejects_invalid_value`).

### 4. Manuella livtester per pilot
- [ ] Ett verkligt samtal genomförs och ordern dyker upp:
  - [ ] i Supabase `public.orders`,
  - [ ] i Lovable/KDS (samma rad),
  - [ ] på lokala dashboarden (`/dashboard?rest_id=...` om relevant).
- [ ] AI lovar inte pickup-tid förrän place_order returnerat success.
- [ ] Avsiktligt felaktigt menynamn → AI ber om förtydligande, ingen order skapas.
- [ ] Vid tre Supabase-insertfel pausas tenant; `incidents` får P0 med
      `human_required=true`.
- [ ] `/admin/ops/run` returnerar `summary` och retryar SMS som varit i kö.
- [ ] `/admin/ops/incidents` listar pågående incidenter.

### 5. Operatör-kanaler
- [ ] Du har minst en notifieringskanal aktiv (logg + extern alert om möjligt).
- [ ] Det finns en runbook för "tenant pausad – vad gör jag?" (kopieras från
      `SUPABASE_SAKERHET_AGENT_PLAN.md` + denna fil).

## Direkt efter golive

- [ ] Verifiera 24h att inga `incidents` med severity P0 är öppna utan åtgärd.
- [ ] Kör `/admin/ops/run` minst varje 60–120 sekunder via Railway cron eller
      separat scheduler.
- [ ] Granska `order_events` dagligen första veckan: bör alltid finnas
      `order_built` + `order_committed` per orderId.

## Rollback-plan

1. Sätt `ORDER_REQUIRE_DB_COMMIT=false` i Railway om Supabase är temporärt nere.
   Då fortsätter ordrar landa i `orders.json` (lokalt) – men varna kunden via
   prompten att SMS kan ta tid.
2. Sätt `DASHBOARD_FROM_DB=false` om dashboarden ska visa `orders.json` istället.
3. Sätt `REQUIRE_DRAFT_TOKEN=false` om en kort prompt-rollback krävs (men då
   återinför vi risken att AI lovar tider innan commit).
4. Pausa Vapi-numret om allt annat misslyckas.
