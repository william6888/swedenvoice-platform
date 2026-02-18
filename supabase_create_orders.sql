-- Skapa orders-tabell för Gislegrillen KDS / Lovable Dashboard
-- Kör i Supabase SQL Editor: https://supabase.com/dashboard/project/_/sql

CREATE TABLE IF NOT EXISTS orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  restaurant_id TEXT NOT NULL DEFAULT 'default',
  customer_name TEXT DEFAULT '',
  customer_phone TEXT DEFAULT '',
  items JSONB NOT NULL DEFAULT '[]',
  total_price NUMERIC(10, 2) NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'NYA',
  raw_transcript TEXT DEFAULT ''
);

-- RLS (Row Level Security) – aktivera om du vill begränsa åtkomst
-- ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Allow insert from service" ON orders FOR INSERT WITH CHECK (true);
-- CREATE POLICY "Allow select" ON orders FOR SELECT USING (true);
