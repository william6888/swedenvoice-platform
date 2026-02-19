# Lovable visar inga ordrar – Lösning

Backend sparar till Supabase. Lovable måste läsa från **samma** Supabase-projekt.

---

## Steg 1: Hämta Supabase-uppgifter

1. Gå till **Supabase Dashboard** → projektet `zgllqocecavcgctbduip`
2. **Project Settings** (kugghjulet) → **API**
3. Kopiera:
   - **Project URL:** `https://zgllqocecavcgctbduip.supabase.co`
   - **anon public** (Under "Project API keys")

---

## Steg 2: Koppla rätt Supabase till Gislegrillen i Lovable

1. Öppna **Lovable** → ditt **Gislegrillen-KDS**-projekt (inte swedenvoice)
2. Gå till projektets **Settings** eller **Integrations**
3. Hitta **Supabase** – om den pekar på swedenvoice eller annat projekt: **ändra** eller **lägg till ny**
4. Ange:
   - **URL:** `https://zgllqocecavcgctbduip.supabase.co`
   - **Anon key:** (den du kopierade)

---

## Steg 3: Läsa från `orders`-tabellen

I Lovable-appens kod/komponenter, se till att du:

1. Hämtar från tabellen **`orders`** (inte `order` eller annat)
2. Använder en query som: `SELECT * FROM orders ORDER BY created_at DESC`
3. Visar kolumnerna: `customer_name`, `customer_phone`, `items`, `total_price`, `status`, `created_at`

---

## Steg 4: Realtime (valfritt – för live-uppdatering)

För att nya ordrar ska dyka upp direkt utan refresh:

1. **Supabase** → **Database** → **Replication**
2. Aktivera Realtime för tabellen **`orders`**
3. I Lovable: använd Supabase Realtime-subscription på `orders`

---

## Snabbtest

1. Kör `python3 test_order.py` (mot Railway eller localhost)
2. Kontrollera i **Supabase** → **Table Editor** → `orders` att raden finns
3. Om raden finns i Supabase men inte i Lovable → Lovable läser från fel projekt eller fel tabell
