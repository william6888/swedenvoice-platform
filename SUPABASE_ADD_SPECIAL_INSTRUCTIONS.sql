-- Kör denna i Supabase SQL Editor (extern databas, public.orders).
-- Krävs en gång så att special_instructions sparas och KDS (Lovable) kan visa specialönskemål.

ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS special_instructions text;

-- raw_transcript bör redan finnas; om den saknas:
-- ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS raw_transcript text;
