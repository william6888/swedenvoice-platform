# Var felet ligger – och hur du bekräftar det

## Flödet (steg för steg)

1. **Vapi** – Du ringer, AI tar order, anropar verktyget `place_order`.
2. **Railway** – Webhook `/vapi/webhook` tar emot anropet.
3. **Backend** – Skapar order, anropar i tur och ordning:
   - Pushover → **du får notis** ✅
   - SMS (Vonage) → **du får SMS** ✅
   - Supabase insert → **här misslyckas det** ❌
4. **Supabase** – Får aldrig raden (senaste rad 12:08, du ringde 16:43).
5. **Lovable** – Läser från Supabase, så när inget kommer in syns inget.

**Alltså:** Felet är **inte** Vapi, **inte** Lovable, **inte** Supabase som “blockerar”. Felet är att **Railway-backend inte lyckas skriva till Supabase** (eller skippar det helt). Pushover + SMS bevisar att anropet når Railway och att ordern processas – Supabase-insert är den enda delen som inte fungerar.

---

## Varför insert misslyckas eller skippas (enda möjligheterna)

1. **SUPABASE_URL eller SUPABASE_KEY saknas/fel i Railway**  
   → Vid start skapas ingen Supabase-klient (`_supabase_client` är None). Varje order: insert skippas, du ser ingen rad i Supabase.

2. **RESTAURANT_UUID saknas i Railway**  
   → Klienten kan finnas men vi skickar inte `restaurant_uuid`; om kolumnen kräver NOT NULL eller FK kan insert ge fel.

3. **Variablerna är satta men deploy har inte körts**  
   → Den körande containern har fortfarande gamla env (tomma eller fel). Spara variabler och **deploya om**.

4. **Nätverk eller Supabase API-fel**  
   → Insert anropet görs men får t.ex. 401/403/500. Då syns "Supabase insert FAILED" i Railway Logs.

---

## Så bekräftar du (gör detta nu)

### A) Debug-endpoint (direkt svar)

Jag har lagt in `/debug-supabase`. **Efter** att du deployat den senaste koden:

Öppna i webbläsaren (eller kör curl):

```
https://web-production-a9a48.up.railway.app/debug-supabase
```

**Förväntat om allt är OK:**
```json
{
  "SUPABASE_URL": "SET",
  "SUPABASE_KEY": "SET",
  "RESTAURANT_UUID": "SET",
  "client_initialized": true,
  "message": "OK – insert till orders ska fungera"
}
```

**Om något är fel:** Du ser t.ex. `"SUPABASE_KEY": "MISSING"` eller `"client_initialized": false` eller `"message": "FEL – Supabase-insert skippas..."`. Då är orsaken att variabeln saknas eller att init misslyckades (fel nyckel/URL). Åtgärd: Sätt/fixa variablerna i Railway och **deploya om**.

### B) Railway Logs (vid nästa samtal/order)

Efter att du ringt eller kört `test_order_railway.py`:

1. Railway → **web** → **Deployments** → senaste → **View Logs**.
2. Sök på **"Supabase"**:
   - **"Supabase client initialized"** vid start → klient skapad.
   - **"Supabase insert SKIPPED: _supabase_client is None"** → URL eller KEY saknas/fel (eller init kraschade).
   - **"✅ Order ... sparad till Supabase"** → insert lyckades.
   - **"⚠️ Supabase insert FAILED"** eller **"Supabase insert failed:"** → insert anropet gjordes men Supabase svarade fel (nyckel, behörighet, nätverk).

---

## Åtgärd (checklist)

1. **Railway → Variables**  
   Kontrollera att dessa finns och är rätt:
   - `SUPABASE_URL` = `https://zgllqocecavcgctbduip.supabase.co`
   - `SUPABASE_KEY` = **Legacy service_role key** (lång JWT från Supabase → Project settings → API)
   - `RESTAURANT_UUID` = `bd525e53-cfb0-4818-a666-90664cd8414f`

2. **Spara och deploya**  
   Efter ändring av variabler: spara och vänta tills en **ny deploy** är klar.

3. **Anropa /debug-supabase**  
   Öppna `https://web-production-a9a48.up.railway.app/debug-supabase`. Om något är MISSING eller `client_initialized` är false → åtgärda enligt punkt 1–2.

4. **Testa order**  
   Kör `python3 test_order_railway.py` eller ring. Kolla Railway Logs efter "sparad till Supabase" eller "insert FAILED/SKIPPED". Kolla Supabase Table Editor att senaste rad är från nu.

---

## Sammanfattning

- **Problemet:** Railway skickar inte ordrar till Supabase (insert skippas eller misslyckas). Pushover + SMS visar att resten av kedjan fungerar.
- **Orsak:** Nästan alltid fel eller saknad **SUPABASE_URL**, **SUPABASE_KEY** eller **RESTAURANT_UUID** på den deployment som faktiskt kör, eller att deploy inte körts efter att du ändrat variabler.
- **Bekräfta:** Använd **/debug-supabase** och **Railway Logs** enligt ovan. Åtgärda variabler, deploya om, testa igen.
