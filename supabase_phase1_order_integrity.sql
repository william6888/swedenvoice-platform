-- =============================================================================
-- Fas 1: Order Integrity Hardening (additiv – bryter inte Lovable eller anon SELECT)
-- =============================================================================
-- Kör i Supabase SQL Editor. Idempotent (IF NOT EXISTS överallt).
-- Förändrar INTE existerande RLS för orders (Lovable måste fortsätta läsa via anon).
-- =============================================================================

-- 1. Komplettera orders-tabellen med tekniska fält som behövs för idempotency,
--    auditing och säkrare statushantering.
alter table public.orders
  add column if not exists vapi_call_id text,
  add column if not exists vapi_tool_call_id text,
  add column if not exists idempotency_key text,
  add column if not exists payload_hash text,
  add column if not exists validation_version text not null default 'phase1',
  add column if not exists needs_human_review boolean not null default false,
  add column if not exists confirmation_token text,
  add column if not exists source text not null default 'vapi';

-- Unik nyckel på idempotency_key så att samtidiga retries ger en enda order.
create unique index if not exists orders_idempotency_key_uidx
  on public.orders (idempotency_key)
  where idempotency_key is not null;

create index if not exists orders_restaurant_created_idx
  on public.orders (restaurant_uuid, created_at desc);

create index if not exists orders_vapi_call_idx
  on public.orders (vapi_call_id)
  where vapi_call_id is not null;

-- Vi tar INTE bort eller ändrar existerande status check-constraint här,
-- för att undvika att redan sparade ordrar blockeras. Validering sker i backend.

-- 2. Audit-logg för orderns livscykel: vapi_received, order_committed,
--    sms_sent, status_changed, needs_review m.fl.
create table if not exists public.order_events (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  restaurant_uuid uuid,
  restaurant_id text,
  order_id text,
  event_type text not null,
  correlation_id text,
  payload jsonb not null default '{}'::jsonb
);

create index if not exists order_events_order_id_idx
  on public.order_events (order_id, created_at);

create index if not exists order_events_restaurant_idx
  on public.order_events (restaurant_uuid, created_at desc);

create index if not exists order_events_correlation_idx
  on public.order_events (correlation_id);

-- 3. Persistent idempotency: motverkar dubblettorder vid Vapi/Railway retries.
create table if not exists public.idempotency_records (
  key text primary key,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  restaurant_uuid uuid,
  restaurant_id text,
  vapi_call_id text,
  vapi_tool_call_id text,
  payload_hash text not null,
  status text not null default 'processing',
  order_id text,
  db_order_id uuid,
  response jsonb,
  error text
);

alter table public.idempotency_records
  drop constraint if exists idempotency_records_status_check;

alter table public.idempotency_records
  add constraint idempotency_records_status_check
  check (status in ('processing', 'completed', 'failed'));

create index if not exists idempotency_restaurant_idx
  on public.idempotency_records (restaurant_uuid, created_at desc);

create index if not exists idempotency_payload_hash_idx
  on public.idempotency_records (restaurant_uuid, payload_hash);

-- 4. Incidents – ops-agentens centrala arbetsobjekt.
create table if not exists public.incidents (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  restaurant_uuid uuid,
  restaurant_id text,
  severity text not null default 'P2',
  type text not null,
  status text not null default 'open',
  human_required boolean not null default false,
  correlation_id text,
  vapi_call_id text,
  order_id text,
  summary text not null default '',
  details jsonb not null default '{}'::jsonb,
  resolved_at timestamptz,
  resolution text
);

alter table public.incidents
  drop constraint if exists incidents_severity_check;

alter table public.incidents
  add constraint incidents_severity_check
  check (severity in ('P0', 'P1', 'P2', 'P3', 'INFO'));

alter table public.incidents
  drop constraint if exists incidents_status_check;

alter table public.incidents
  add constraint incidents_status_check
  check (status in ('open', 'acknowledged', 'auto_resolved', 'resolved', 'closed'));

create index if not exists incidents_restaurant_idx
  on public.incidents (restaurant_uuid, created_at desc);

create index if not exists incidents_status_idx
  on public.incidents (status, severity, created_at desc);

-- 5. Audit-logg för alla autonoma åtgärder (read-only för admin/ägare).
create table if not exists public.ops_actions (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  restaurant_uuid uuid,
  restaurant_id text,
  incident_id uuid references public.incidents(id) on delete set null,
  action text not null,
  reason text not null default '',
  result text not null default 'ok',
  reversible boolean not null default true,
  details jsonb not null default '{}'::jsonb
);

create index if not exists ops_actions_restaurant_idx
  on public.ops_actions (restaurant_uuid, created_at desc);

create index if not exists ops_actions_action_idx
  on public.ops_actions (action, created_at desc);

-- 6. SMS-jobb: agenten kan retrya/dead-letter utan att blockera order-hot-path.
create table if not exists public.sms_jobs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  restaurant_uuid uuid,
  restaurant_id text,
  order_id text,
  db_order_id uuid,
  to_number text,
  body text,
  status text not null default 'pending',
  attempts int not null default 0,
  max_attempts int not null default 3,
  next_attempt_at timestamptz not null default now(),
  last_error text default ''
);

alter table public.sms_jobs
  drop constraint if exists sms_jobs_status_check;

alter table public.sms_jobs
  add constraint sms_jobs_status_check
  check (status in ('pending', 'sending', 'sent', 'failed', 'dead_letter', 'blocked', 'missing_phone'));

create index if not exists sms_jobs_status_idx
  on public.sms_jobs (status, next_attempt_at);

create index if not exists sms_jobs_order_idx
  on public.sms_jobs (order_id);

-- 7. Tenant-hälsa: aktuell driftstatus per pizzeria. Agenten uppdaterar denna.
create table if not exists public.tenant_health (
  restaurant_uuid uuid primary key,
  restaurant_id text,
  intake_status text not null default 'open',
  intake_paused_reason text default '',
  last_supabase_ok timestamptz,
  last_sms_ok timestamptz,
  last_order_committed timestamptz,
  consecutive_supabase_failures int not null default 0,
  consecutive_sms_failures int not null default 0,
  updated_at timestamptz not null default now()
);

alter table public.tenant_health
  drop constraint if exists tenant_health_intake_status_check;

alter table public.tenant_health
  add constraint tenant_health_intake_status_check
  check (intake_status in ('open', 'paused', 'degraded'));

-- =============================================================================
-- RLS-anteckning (medvetet val):
--   * Vi aktiverar RLS endast på de NYA tabellerna (defense-in-depth) och tillåter
--     bara service_role att läsa/skriva. Backend använder service_role och
--     påverkas inte. Lovable använder anon-nyckel och har INTE access hit.
--   * Vi rör INTE RLS på orders – Lovables anon SELECT måste fortsätta fungera
--     enligt SUPABASE_SAKERHET_AGENT_PLAN.md.
-- =============================================================================

alter table public.idempotency_records enable row level security;
alter table public.order_events enable row level security;
alter table public.incidents enable row level security;
alter table public.ops_actions enable row level security;
alter table public.sms_jobs enable row level security;
alter table public.tenant_health enable row level security;

-- Inga policies = endast service_role har access (RLS blockerar anon/authenticated).
-- Detta är medvetet: ops-agent och backend kör med service_role.
