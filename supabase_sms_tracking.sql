-- SMS-spårning för orderbekräftelser.
-- Körs säkert flera gånger: lägger bara till saknade kolumner.

ALTER TABLE public.orders
  ADD COLUMN IF NOT EXISTS order_id text,
  ADD COLUMN IF NOT EXISTS sms_status text NOT NULL DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS sms_to text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS sms_last_error text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS sms_sent_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_orders_order_id
  ON public.orders (order_id);

CREATE INDEX IF NOT EXISTS idx_orders_sms_status
  ON public.orders (sms_status);
