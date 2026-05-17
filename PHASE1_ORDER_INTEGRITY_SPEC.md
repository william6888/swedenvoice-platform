# Fas 1 Teknisk Spec: Order Integrity Hardening

## Syfte

Fas 1 ska göra orderkedjan robust nog för en kontrollerad pilot. Fokus är inte fler features, utan garantier:

- Exakt en order per bekräftad kundbeställning.
- Ingen falsk success om ordern inte är sparad i system of record.
- Samma datakälla för backend, kök och extern KDS.
- Tydlig validering innan något når köket.

## Scope

Ingår:

- Persistent idempotency.
- Supabase/Postgres som primär orderkälla.
- Strikt inputvalidering.
- `id/name` invariant.
- Status enum.
- Dashboard läser Supabase.
- Tester för retry, concurrency och failure modes.

Ingår inte i Fas 1:

- Betalningar.
- Kundprofiler.
- POS-sync.
- Full modifierar-/toppingsmodell.
- Autonom ops-agent.
- Ny frontend-arkitektur.

## Datamodell

### `orders`

Behåll befintliga orderfält men komplettera med stabila tekniska fält:

```sql
alter table public.orders
  add column if not exists order_id text unique,
  add column if not exists restaurant_uuid uuid,
  add column if not exists vapi_call_id text,
  add column if not exists vapi_tool_call_id text,
  add column if not exists idempotency_key text,
  add column if not exists payload_hash text,
  add column if not exists source text not null default 'vapi',
  add column if not exists status text not null default 'pending',
  add column if not exists special_instructions text default '',
  add column if not exists validation_version text not null default 'phase1';
```

Constraints:

```sql
alter table public.orders
  add constraint orders_status_check
  check (status in ('pending', 'ready', 'completed', 'cancelled', 'failed'));

create unique index if not exists orders_idempotency_key_uidx
  on public.orders (idempotency_key)
  where idempotency_key is not null;

create index if not exists orders_restaurant_created_idx
  on public.orders (restaurant_uuid, created_at desc);
```

### `order_events`

Audit-logg för orderns livscykel:

```sql
create table if not exists public.order_events (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  restaurant_uuid uuid,
  order_id text,
  event_type text not null,
  correlation_id text,
  payload jsonb not null default '{}'::jsonb
);

create index if not exists order_events_order_id_idx
  on public.order_events (order_id, created_at);
```

### `idempotency_records`

Separat tabell ger tydligare retry-beteende och felsökning:

```sql
create table if not exists public.idempotency_records (
  key text primary key,
  created_at timestamptz not null default now(),
  restaurant_uuid uuid,
  vapi_call_id text,
  vapi_tool_call_id text,
  payload_hash text not null,
  status text not null default 'processing',
  order_id text,
  response jsonb,
  error text
);

alter table public.idempotency_records
  add constraint idempotency_records_status_check
  check (status in ('processing', 'completed', 'failed'));
```

## Idempotency-Nyckel

Primär nyckel:

```text
restaurant_uuid:vapi_call_id:vapi_tool_call_id
```

Fallback om `tool_call_id` saknas:

```text
restaurant_uuid:vapi_call_id:sha256(canonical_payload)
```

Fallback om `call_id` saknas:

```text
restaurant_uuid:direct:sha256(canonical_payload)
```

Canonical payload ska innehålla:

- Canonical resolved item ids.
- Quantity.
- Per-item special requests.
- Order-level special requests.
- Restaurant/tenant.

Den ska inte innehålla timestamps, random order ids eller fältordning.

## Backend-Flöde

Ny hot path:

1. Verifiera webhook secret.
2. Extrahera `rest_id`, `call_id`, `tool_call_id`.
3. Parse:a items.
4. Validera rå input.
5. Matcha mot meny.
6. Kontrollera `id/name` invariant.
7. Skapa canonical payload och idempotency key.
8. Starta idempotent commit mot Supabase.
9. Om key redan är `completed`: returnera sparat response.
10. Om key är `processing`: returnera kontrollerat retry-svar eller vänta kort.
11. Insert order i Supabase.
12. Insert `order_events`.
13. Markera idempotency record som `completed`.
14. Returnera success till Vapi.
15. Trigga SMS/jobbar efter commit.

## Kodändringar

### `main.py`

Föreslagna nya funktioner:

- `build_canonical_order_payload(resolved_items, special_requests, restaurant_uuid) -> dict`
- `build_payload_hash(canonical_payload) -> str`
- `build_idempotency_key(restaurant_uuid, call_id, tool_call_id, payload_hash) -> str`
- `validate_order_items(raw_items) -> None`
- `validate_id_name_consistency(item, menu_index) -> None`
- `create_order_in_supabase_idempotent(...) -> OrderCommitResult`
- `get_orders_from_supabase(restaurant_uuid) -> list`
- `update_order_status_in_supabase(order_id, status, restaurant_uuid) -> None`
- `record_order_event(event_type, order_id, payload, correlation_id) -> None`

Funktioner som ska nedgraderas eller flyttas bort från hot path:

- `load_orders`
- `save_orders`
- `_process_place_order` som filskrivande funktion

De kan behållas för lokal debug, men produktionsflödet ska inte bero på dem.

### `menu_match.py`

Ändra regel:

- Om `id` och `name` båda finns måste de matcha samma canonical item.
- Om de inte matchar ska raden läggas i `unmatchedItems` med typen `id_name_mismatch`.
- Vapi ska då fråga kunden om rätt rätt istället för att backend gissar.

### `index.html`

I Fas 1 kan dashboarden fortsatt vara vanilla JS, men den ska:

- Hämta order från Supabase-backed `/orders`.
- Skicka status till Supabase-backed `/update_order_status`.
- Rendera kundstyrd text med `textContent` eller explicit escaping.
- Acceptera bara serverns kända statusvärden.

Auth kan implementeras i Fas 3 om Fas 1 körs i privat pilotmiljö, men publik go-live kräver auth innan lansering.

## API-Kontrakt

### Success

```json
{
  "success": true,
  "order_id": "GG-20260516-123456",
  "total_price": 250,
  "idempotency_key": "restaurant:call:tool",
  "status": "pending"
}
```

### Retry

Samma request ska returnera samma success-response:

```json
{
  "success": true,
  "order_id": "GG-20260516-123456",
  "total_price": 250,
  "idempotent_replay": true,
  "status": "pending"
}
```

### Validation Failure

```json
{
  "success": false,
  "error": "En eller flera artiklar kunde inte verifieras.",
  "unmatchedItems": [
    {
      "index": 0,
      "input": "Kebabpizza",
      "match": {
        "type": "id_name_mismatch",
        "sentId": 13,
        "sentName": "Kebabpizza",
        "canonicalNameForId": "Bahamas"
      }
    }
  ]
}
```

### Dependency Failure

Om Supabase inte kan skriva ordern:

```json
{
  "success": false,
  "error": "Beställningen kunde inte sparas just nu. Försök igen."
}
```

Backend får inte returnera order-id i detta läge.

## Tester

### Unit Tests

- `quantity=0` avvisas.
- `quantity=-1` avvisas.
- Extremt hög quantity avvisas.
- Tom order avvisas.
- För lång `special_requests` avvisas.
- `id/name` mismatch avvisas.
- `fuzzy_ambiguous` skapar inte order.
- `idempotency_key` är stabil för samma canonical payload.

### Integration Tests

- Samma tool-call payload fem gånger skapar en order.
- Samma payload parallellt från två requests skapar en order.
- Retry efter successful commit returnerar samma order-id.
- Supabase insert-fel returnerar `success:false`.
- Dashboard `GET /orders` läser Supabase.
- Statusuppdatering skriver Supabase och validerar status.

### Regression Tests

- Vapi `toolCalls`, `toolCallList` och `toolWithToolCallList` fungerar.
- Direct payload fungerar.
- `end-of-call-report` skapar inte order.
- SMS-fel påverkar inte committed order.

## Rollout

1. Kör migrationer i staging.
2. Kör unit och integrationstester.
3. Kör Vapi testcall mot staging.
4. Verifiera att order syns i Supabase och dashboard.
5. Simulera retry och concurrency.
6. Aktivera för en pilotpizzeria.
7. Följ metrics och incidenter under minst en rush-period.

## Definition Of Done

Fas 1 är klar när:

- `orders.json` inte längre är primär orderkälla i produktion.
- Supabase är enda sanning för order och status.
- Persistent idempotency finns och är testad.
- Alla P0-risker i `LIVE_READINESS_AUDIT.md` kopplade till orderintegritet är stängda.
- CI täcker retry, concurrency och validering.
- Man kan visa en logg/audit trail från samtal till köksorder.
