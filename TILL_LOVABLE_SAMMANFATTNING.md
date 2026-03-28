# Sammanfattning till Lovable – specialönskemål (special_instructions)

**Du kan kopiera texten nedan och skicka till Lovable.**

---

## Vad vi (backend/Cursor) har gjort – klart

1. **Supabase**
   - Kolumnen **`special_instructions`** (text) är tillagd i **`public.orders`** i den externa Supabase-databasen.
   - Backend skickar nu alltid med **`special_instructions`** (och valfritt **`raw_transcript`**) vid varje order-insert.

2. **Backend (FastAPI / Railway)**
   - När Vapi anropar `place_order` med parametern **`special_requests`** (t.ex. "extra sås", "utan lök") sparar vi det i orderobjektet och skickar det till Supabase som **`special_instructions`**.
   - Vi skickar även **per-rätt-anteckningar** i **`items`**-JSON under nyckeln **`notes`** (om kunden sagt t.ex. "Vesuvio med extra sås").
   - Om kolumnen `special_instructions` skulle saknas i databasen gör backend en automatisk fallback (order sparas ändå, utan det fältet).

3. **Vapi / AI-prompt**
   - System-prompten är uppdaterad så att AI:n **alltid ska fylla i `special_requests`** när kunden sagt specialönskemål (t.ex. "extra sås", "utan lök"). Tidigare stod det inte explicit, så AI:n skickade ofta bara `items` utan `special_requests` – därför syntes inte "extra sås" i databasen eller i köket.
   - Efter denna ändring ska nya samtal fylla i `special_requests` korrekt, så att backend kan skriva till **`special_instructions`** i Supabase.

**Sammanfattning från vår sida:** Allt är klart. Databasen har kolumnen, backend skickar värdet, och AI-prompten är justerad så att specialönskemål skickas med från Vapi.

---

## Varför "extra sås" inte kom med i din testbeställning

- **Orsak:** AI:n (Vapi/Groq) anropade `place_order` med bara **`items`** och skickade **inte** parametern **`special_requests`**. Det stod inte i system-prompten att den måste fylla i den.
- **Åtgärd:** Vi har uppdaterat **system_prompt.md** så att det uttryckligen står att AI:n ska skicka med **`special_requests`** när kunden sagt t.ex. "extra sås", "utan lök", etc. Den nya prompten måste **kopieras in i Vapi Assistant** (Model → System prompt) så att den används. Därefter ska nya samtal fylla i `special_requests`, och då hamnar texten i **`special_instructions`** i Supabase och kan visas i Lovable.

---

## Vad vi behöver från Lovable

1. **Bekräfta att KDS (köksvyn) visar `special_instructions`**  
   Ordertabellen i den externa Supabase har nu kolumnen **`special_instructions`**. Kontrollera att er app läser och visar detta fält på orderkorten (ni skrev tidigare att ni är redo med varningsikon för specialönskemål – då räcker det att ni använder kolumnen **`special_instructions`** från `orders`).

2. **Om ni vill visa per-rätt-anteckningar**  
   Backend skickar även **`notes`** per rad i **`items`**-arrayen (t.ex. `{"id": 2, "name": "Vesuvio", "quantity": 1, "price": 125, "notes": "extra sås"}`). Om ni vill visa det per rad kan ni använda **`items[].notes`** i er UI.

3. **Inga fler ändringar behövs från backend**  
   Vi kommer inte att ändra API eller datastruktur ytterligare för specialönskemål. När ni visar **`special_instructions`** (och eventuellt **`items[].notes`**) är kedjan sluten.

---

## Checklista (för er egen koll)

- [ ] **Supabase (extern DB):** Kolumnen **`special_instructions`** finns i **`public.orders`**. ✅ (vi har kört ALTER TABLE.)
- [ ] **Backend:** Skickar **`special_instructions`** och **`items[].notes`** vid insert. ✅ (implementerat.)
- [ ] **Vapi:** System-prompten i Assistant innehåller instruktionen att alltid fylla i **`special_requests`** vid specialönskemål. ⬅️ **Vi har uppdaterat filen – användaren måste klistra in den nya prompten i Vapi Assistant.**
- [ ] **Lovable:** KDS visar **`special_instructions`** (och ev. **`items[].notes`**) på orderkorten. ⬅️ **För Lovable att bekräfta.**

När både den nya prompten används i Vapi och Lovable visar **`special_instructions`** kommer "extra sås" och andra specialönskemål att synas i köket från beställning till visning.

---

*Sammanfattning skriven från backend/Cursor-sidan. Allt är klartecken från vår sida.*
