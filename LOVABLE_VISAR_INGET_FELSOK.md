# Lovable visar inget – hitta grundorsaken

Kedjan: **Railway → Supabase → Edge-funktion → Köksvy**. Ett steg måste brista. Gå igenom nedan i ordning.

---

## Steg 1: Finns ordern i Supabase? (gör du eller Supabase)

Om ordern **inte** finns här är problemet i Railway/backend, inte Lovable.

**A) Du:** Supabase Dashboard → Table Editor → projekt **zgllqocecavcgctbduip** → tabell **orders**. Sortera på **created_at** (senast först). Ser du senaste ordern (t.ex. från `python3 test_order_railway.py`)? Notera om **restaurant_id** = `Gislegrillen_01`.

**B) Eller skriv till Supabase:**  
"Kör: SELECT id, restaurant_id, restaurant_uuid, status, created_at FROM public.orders ORDER BY created_at DESC LIMIT 5; och visa resultatet. Jag behöver veta om ordrar med restaurant_id = 'Gislegrillen_01' finns."

**Resultat:**
- **Ordrar finns med Gislegrillen_01** → gå till Steg 2.
- **Inga ordrar eller annat restaurant_id** → problemet är att Railway inte sparar till Supabase eller sparar fel. Kolla Railway Variables (SUPABASE_URL, SUPABASE_KEY, RESTAURANT_UUID) och Railway Logs efter "Supabase insert".

---

## Steg 2: Returnerar edge-funktionen data? (Lovable)

Om Supabase har ordrar men edge-funktionen returnerar tomt, är problemet konfiguration (URL/nyckel/filter) eller RLS.

**Skriv till Lovable:**

"Våra ordrar finns i extern Supabase (zgllqocecavcgctbduip) med restaurant_id = 'Gislegrillen_01'. Gör följande och svara med exakt resultat:

1. Anropa edge-funktionen get-external-orders manuellt (eller kör en test som anropar den) och visa **råa svaret** (JSON). Returnerar den en array med ordrar eller []?
2. Om den returnerar []: använder edge-funktionen URL https://zgllqocecavcgctbduip.supabase.co och EXTERNAL_SUPABASE_ANON_KEY för det projektet? Filtrerar den på restaurant_id = 'Gislegrillen_01'?
3. Om den använder rätt URL och nyckel men får []: kan RLS i extern Supabase blockera anon? (Vi har anon SELECT USING (true) – be mig dubbelkolla med Supabase om du vill.)
4. Lista eventuella felmeddelanden eller statuskoder från anropet till den externa Supabase."

**Du kan också (Supabase):** Be Supabase köra:  
"Lista alla RLS-policies på public.orders. Finns en policy FOR SELECT TO anon?"  
Om anon SELECT saknas → be Supabase lägga till den (se VAD_SKA_JAG_GÖRA.md avsnitt 2C).

---

## Steg 3: Anropar köksvyn edge-funktionen? (Lovable + du)

Kanske anropet inte sker, eller fel endpoint, eller frontend visar inte det som returneras.

**Du (webbläsaren):** Öppna köksvyn i Lovable (inloggad). Öppna **Utvecklarverktyg** (F12) → **Nätverk** (Network). Ladda om sidan. Sök efter anrop som innehåller "external" eller "orders". Klicka på anropet – vad är **URL**, **Status** (200/4xx/5xx) och **Svar** (Response)? Om du inte ser något anrop till get-external-orders anropar inte frontend den.

**Skriv till Lovable:**

"När jag laddar köksvyn ser jag i Network-fliken [beskriv vad du ser: anrop till get-external-orders? statuskod? svar tomt eller med data?]. Visar köksvyn komponenten data från det anropet, eller från någon annan källa? Om anropet returnerar ordrar men skärmen är tom – var filtreras eller ignoreras datan i frontend (vilken komponent, vilken state)?"

---

## Steg 4: Inloggning och fel i konsolen

**Du:** Samma sida, Utvecklarverktyg → **Konsol** (Console). Finns det röd felmeddelanden när köksvyn laddas? Kopiera dem.

**Skriv till Lovable (om du ser fel):**

"På köksvyn får jag dessa konsolfel: [klistra in]. Vad betyder de och hur åtgärdar vi så att ordrar laddas?"

---

## Sammanfattning – var kan grundorsaken vara?

| Om … | Då är grundorsaken troligen … |
|------|--------------------------------|
| Inga ordrar i Supabase | Railway sparar inte (env, fel i backend). |
| Ordrar i Supabase men edge returnerar [] | Fel URL/nyckel i edge, eller fel filter (restaurant_id), eller RLS blockar anon. |
| Edge returnerar ordrar men köksvyn tom | Frontend anropar inte edge, eller använder inte svaret (fel state/komponent). |
| Konsol-fel vid laddning | JavaScript-fel eller fel från API-anrop – åtgärda enligt Lovables råd. |

---

## Text du kan klistra in till Supabase (en grej)

"Jag får inte fram ordrar i Lovable. För att utesluta att det är RLS: Kör SELECT id, restaurant_id, created_at FROM public.orders WHERE restaurant_id = 'Gislegrillen_01' ORDER BY created_at DESC LIMIT 3; och visa resultatet. Lista sedan alla RLS-policies på public.orders – finns FOR SELECT TO anon med USING (true)? Svara med resultat + policy-lista."

---

## Text du kan klistra in till Lovable (en grej)

"Ordrar med restaurant_id 'Gislegrillen_01' finns i extern Supabase (zgllqocecavcgctbduip) men syns inte i köksvyn. Gör detta och svara med exakt svar: (1) Anropa get-external-orders och visa rå JSON-svar – får ni ordrar eller []? (2) Om []: kontrollera att edge använder https://zgllqocecavcgctbduip.supabase.co och rätt anon-nyckel och filter restaurant_id = 'Gislegrillen_01'. (3) Om edge returnerar ordrar: vilken komponent visar kökslistan och får den denna data – varför skulle skärmen vara tom? (4) Krävs inloggning för att anropet ska ske, och är användaren inloggad?"

När du har svar från Steg 1 (Supabase) och Steg 2–4 (Lovable + egen koll) vet du var kedjan bryts. Skicka gärna deras svar hit så kan vi formulera nästa steg.
