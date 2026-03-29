# Deploya Gislegrillen till Railway

## 1. Förberedelser

- Konto på [railway.app](https://railway.app)
- Projektet klonat/öppet lokalt

## 2. Deploy via GitHub (rekommenderat)

1. **Pusha till GitHub** (om inte redan gjort):
   ```bash
   git add .
   git commit -m "Railway deployment"
   git push origin main
   ```

2. **Skapa nytt projekt i Railway:**
   - Gå till [railway.app](https://railway.app) → New Project
   - Välj **Deploy from GitHub repo**
   - Välj ditt Gislegrillen-repo

3. **Lägg till variabler** (Settings → Variables) – se tabellen nedan (minst `VAPI_API_KEY`, Supabase och ev. Vonage).

4. **Generera publik URL:**
   - Settings → Networking → Generate Domain
   - Du får t.ex. `gislegrillen-production-xxxx.up.railway.app`

## 3. Deploy via Railway CLI

```bash
# Installera CLI (om du inte har den)
npm install -g @railway/cli

# Logga in med din token
railway login
# Eller: railway login --token DIN_TOKEN

# I projektmappen
cd /Users/williamlarsson/Gislegrillen_
railway init   # Skapa nytt projekt (första gången)
railway up     # Deploya
```

Efter deploy: Settings → Networking → Generate Domain.

## 4. Sätt variabler i Railway

I Railway Dashboard → ditt projekt → Variables, lägg till (kopiera från .env):

| Variabel | Värde |
|----------|-------|
| VAPI_API_KEY | (från .env) |
| SUPABASE_URL | (från .env) |
| SUPABASE_KEY | (service_role JWT från .env) |
| VONAGE_API_KEY | (från .env) |
| VONAGE_API_SECRET | (från .env) |
| VONAGE_FROM_NUMBER | E.164, t.ex. `+46769439831` (ditt Vonage SMS-avsändarnummer) |

## 5. Uppdatera Vapi

1. Vapi Dashboard → Assistant → Advanced → Server Settings
2. **Server URL:** `https://DIN-RAILWAY-URL.up.railway.app/vapi/webhook`
3. Ta bort headern `ngrok-skip-browser-warning` (behövs inte med Railway)

## 6. Kontrollera

```bash
curl https://DIN-RAILWAY-URL.up.railway.app/health
```

---

**Obs:** Din Railway-token används bara för `railway login` – lägg den INTE i .env eller i koden.
