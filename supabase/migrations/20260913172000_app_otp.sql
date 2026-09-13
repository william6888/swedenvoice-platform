-- OTP for customer app. Service role only; survives Railway deploys.
create table if not exists public.app_otp (
  phone text primary key,
  code_hash text not null,
  expires_at timestamptz not null,
  attempts integer not null default 0,
  updated_at timestamptz not null default now()
);

alter table public.app_otp enable row level security;
-- No policies: anon/authenticated cannot read. Backend uses service_role.
