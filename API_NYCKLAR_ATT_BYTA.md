# API-nycklar som används – vilka du ska byta om något har läckt

Om några nycklar har läckt (t.ex. committade till GitHub, delade i chatt eller skärmdumpar): **byt alla nedan** och uppdatera både lokalt (`.env`) och i **Railway → Variables**. Skriv **aldrig** de riktiga nyckelvärdena i denna fil eller i chatten.

---

## Lista över känsliga nycklar (namn på variablerna)

| Variabel | Var du byter nyckeln | Kommentar |
|----------|----------------------|-----------|
| **VAPI_API_KEY** | [vapi.ai](https://vapi.ai) → Dashboard → API Keys | Skapa ny, ta bort gammal. Uppdatera i .env och Railway. |
| **GROQ_API_KEY** | [console.groq.com](https://console.groq.com) → API Keys | Skapa ny key, radera gammal. Uppdatera i .env och i Vapi (om du satt Groq där). |
| **PUSHOVER_USER_KEY** | [pushover.net](https://pushover.net) → din profil | User key – byt inte ofta; om läckt, skapa nytt konto eller kontakta Pushover. |
| **PUSHOVER_API_TOKEN** | [pushover.net](https://pushover.net) → Applications | Skapa ny app, ny token. Uppdatera .env och Railway. |
| **VONAGE_API_KEY** | [dashboard.nexmo.com](https://dashboard.nexmo.com) | API Key + Secret – kan rotera/regenerera. Uppdatera .env och Railway. |
| **VONAGE_API_SECRET** | [dashboard.nexmo.com](https://dashboard.nexmo.com) | Byt tillsammans med VONAGE_API_KEY. |
| **SUPABASE_KEY** | [supabase.com](https://supabase.com) → Project Settings → API | Anon key eller service role. Kan rotera (generera ny). Uppdatera .env, Railway och **Lovable** (samma Supabase). |
| **ADMIN_SECRET** | Du väljer själv | Valfri lång hemlig sträng. Byt till ny sträng i .env och Railway. |
| **ENCRYPTION_SECRET** | Du väljer själv | Om du använder Fas 2 (restaurant_secrets). Minst 32 tecken. Byt i .env och Railway. |
| **PUSHOVER_ALERTS_USER_KEY** | [pushover.net](https://pushover.net) | Om du använder separat Pushover för alerts. Annars används PUSHOVER_USER_KEY. |
| **PUSHOVER_ALERTS_TOKEN** | [pushover.net](https://pushover.net) | Samma som ovan. |

**Inte nycklar men känsliga:**  
- **SUPABASE_URL** – om den läckt kan någon veta vilket projekt du använder; byt inte om bara URL läckt, men **SUPABASE_KEY** måste bytas om den läckt.  
- **VONAGE_FROM_NUMBER** – ett telefonnummer; byt inte som “nyckel” men om det läckt kan du behöva byta nummer hos Vonage.

---

## Steg när du byter (säkert)

1. **Byt nyckeln i respektive tjänst** (Vapi, Groq, Pushover, Vonage, Supabase) – skapa ny / rotera, inaktivera eller radera gammal.
2. **Uppdatera lokalt:** Redigera `.env` (ersätt inte hela filen i chatten – bara på din dator).
3. **Uppdatera Railway:** Projekt → Variables → redigera varje variabel till det nya värdet.
4. **Om du bytte SUPABASE_KEY:** Uppdatera även i **Lovable** (projektets Supabase-koppling med samma anon key).
5. **Om du bytte GROQ eller VAPI:** Kolla att **Vapi** fortfarande har rätt API-nyckel (Vapi använder ofta Groq via sin egen koppling).
6. **Kontrollera .gitignore:** Säkerställ att `.env` finns med i `.gitignore` så att du aldrig committar nycklar igen.

---

## Om nycklar redan committade till GitHub

- **Byt alla nycklar ovan** – att ta bort filen i senare commit gör inte gamla nycklar ogiltiga; de finns kvar i historiken.
- Överväg att **radera repot** eller använda [GitHub’s guide](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) för att ta bort känslig data från historik (git filter-branch eller BFG). Detta påverkar alla som klonat repot.

---

*Denna fil innehåller inga riktiga nyckelvärden – bara namn på variabler och var du byter dem.*
