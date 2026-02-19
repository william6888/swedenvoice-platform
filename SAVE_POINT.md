# SAVE – återställningspunkt (senast 100 % fungerande)

**Datum:** Innan vi börjar bygga Fas 1/2/3 (circuit breaker, config-cache, restaurant_secrets, etc.)

**Status vid denna punkt:** Allt fungerar. Railway online, webhook, tenant lookup (rest_id), call_id-cache, Supabase, Lovable, Pushover, SMS. Inga kända fel.

---

## Hur du går tillbaka hit om något går sönder

Om det ni bygger (Fas 1, 2 eller 3) krashar Railway, ger olösliga problem eller bara måste rullas tillbaka:

### Alternativ A: Återställ lokalt till save-point

```bash
# Kasta alla lokala ändringar och gå tillbaka till save-point
git fetch origin
git checkout stable-working-pre-fas1
# Eller: git reset --hard stable-working-pre-fas1   (om du är på main och vill att main ska peka hit)
```

Efter det: pusha till Railway (om du vill att Railway också ska köra denna version):

```bash
git checkout main
git reset --hard stable-working-pre-fas1
git push origin main --force
```

**OBS:** `--force` skriver över `main` på GitHub. Använd bara om du verkligen vill rulla tillbaka hela projektet.

### Alternativ B: Deploya backup-branchen på Railway

Om Railway är kopplat till GitHub kan du i Railway byta vilken **branch** som deployas:

1. Railway → ditt projekt → Settings (eller Deployments).
2. Ändra "Branch" från `main` till `backup/stable-working`.
3. Triggera en ny deploy.

Då kör Railway koden från backup-branchen (samma som denna save-point) utan att du behöver skriva över `main`.

### Alternativ C: Bara ta fram filerna lokalt (utan att ändra main)

```bash
git checkout backup/stable-working
# Nu har du alla filer som vid save-point. Kopiera vad du behöver, eller jobba här.
# För att gå tillbaka till main: git checkout main
```

---

## Vad som är sparát

- **Tagg:** `stable-working-pre-fas1` (pekar på commit med indentation-fix, multi-tenant, call_id-cache, request-isolering – senast verifierat fungerande på Railway).
- **Branch:** `backup/stable-working` (samma commit).

**Viktigt:** Tagg och branch är redan pushade till GitHub. Om du klonat repot på en annan dator: `git fetch --tags` så att taggen syns.

---

## Har du allt? (så du inte missar något)

| Vad | Var det sparát? | Vid återställning |
|-----|-----------------|-------------------|
| **Kod (main.py, requirements.txt, Procfile, etc.)** | Ja – allt som finns i commit 2a81c63. | Du får exakt den koden med `git checkout stable-working-pre-fas1` eller branchen `backup/stable-working`. |
| **.env (lokal)** | Nej – .env committas inte (hemligheter). | Behåll en lokal kopia av .env, eller återskapa från .env.template. Railway påverkas inte av git; dina Railway-variabler är oförändrade. |
| **Railway-variabler** | Nej – de ligger i Railway, inte i git. | Vid återställning av kod ändras de inte. Om du skapat om Railway-projektet måste du sätta variablerna igen (SUPABASE_URL, SUPABASE_KEY, RESTAURANT_UUID, etc.) från .env.template. |
| **Supabase / Vapi / Lovable** | Nej – databas och tjänster är utanför repot. | Återställning av kod påverkar inte dem. Samma DB, samma Vapi-URL, samma Lovable. |

**Verifiera efter återställning:** Kör `python3 test_order_railway.py` (mot Railway-URL). Ska ge 200 och order_id om allt är som det ska.
