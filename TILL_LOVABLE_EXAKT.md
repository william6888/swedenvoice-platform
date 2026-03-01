# Till Lovable – exakt sammanfattning: special_instructions

**Kopiera och skicka detta till Lovable.**

---

## Vad vi har gjort (backend + Supabase) – klart

1. **Supabase (extern databas, public.orders)**  
   Vi har lagt till kolumnen **`special_instructions`** (typ `text`) i tabellen **`orders`**.  
   Varje ny order som backend skickar in innehåller nu detta fält.

2. **Backend (FastAPI på Railway)**  
   När Vapi anropar `place_order` med parametern **`special_requests`** (t.ex. "Vesuvio: extra sås") gör vi följande:
   - Vi sparar värdet i orderobjektet.
   - Vid insert till Supabase skickar vi det i kolumnen **`special_instructions`**.
   - Vi skickar också per-rätt-anteckningar i **`items`** under nyckeln **`notes`** (t.ex. `{"id": 2, "name": "Vesuvio", "quantity": 1, "price": 125, "notes": "extra sås"}`).

3. **Vapi / AI**  
   System-prompten i Vapi är uppdaterad så att AI:n ska skicka med **`special_requests`** när kunden sagt t.ex. extra sås eller utan lök. Backend tar emot det och skriver till Supabase som ovan.

**Kontroll från vår sida:** Nya ordrar i Supabase har alltså fyllt i **`special_instructions`** (och eventuellt **`items[].notes`**) när kunden sagt specialönskemål. Det är klart från backend och databas.

---

## Vad Lovable måste göra så att det blir rätt

KDS-appen (Lovable) läser från **samma externa Supabase** och tabellen **`public.orders`**. För att specialönskemål ska synas i köket måste ni:

### 1. Läsa ut kolumnen `special_instructions`

- Varje rad i **`orders`** har nu kolumnen **`special_instructions`** (text).
- När ni hämtar ordrar (t.ex. via er edge-funktion eller Supabase-klient) måste ni **inkludera** detta fält i ert anrop/query.
- Exempel (om ni använder select):  
  `SELECT id, restaurant_id, customer_name, customer_phone, items, total_price, status, created_at, special_instructions FROM public.orders ...`  
  eller `SELECT * FROM public.orders` (då följer `special_instructions` med).

### 2. Visa `special_instructions` på orderkortet

- När ni renderar ett orderkort i köksvyn: visa värdet från **`special_instructions`**.
- Om **`special_instructions`** är tomt eller null, visa inget (eller dölj sektionen).
- Om det finns text (t.ex. "Vesuvio: extra sås. Kebabpizza: utan lök."), visa den tydligt på kortet – t.ex. under orderraderna eller med en liten varningsikon så att köket ser specialönskemålen.

### 3. (Valfritt) Per-rätt-anteckningar i `items`

- I **`items`**-arrayen kan varje objekt ha en nyckel **`notes`** (sträng), t.ex.  
  `{"id": 2, "name": "Vesuvio", "quantity": 1, "price": 125, "notes": "extra sås"}`.
- Om ni vill visa specialönskemål per rad kan ni läsa **`item.notes`** och visa det bredvid respektive rätt på orderkortet.

---

## Kort checklista för Lovable

- [ ] Er query/API mot **`public.orders`** inkluderar kolumnen **`special_instructions`** (eller ni använder `SELECT *` så att den följer med).
- [ ] Orderkortet i KDS visar **`special_instructions`** när fältet har innehåll.
- [ ] (Valfritt) Ni visar **`items[].notes`** per rad om ni vill ha per-rätt-anteckningar.

När dessa tre punkter är uppfyllda kommer specialönskemål från samtalet att synas i köket. All data skickas redan från vår sida till Supabase; det som saknas är att Lovable läser och visar **`special_instructions`** (och eventuellt **`items[].notes`**) i er app.

---

*Sammanfattning från backend/Cursor. Allt är klart från vår sida; Lovable behöver läsa och visa `special_instructions` (och valfritt `items[].notes`) i KDS.*
