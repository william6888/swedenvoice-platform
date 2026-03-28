# Så deployar du (enkelt)

Jag (AI) kan **inte** logga in på ditt Railway-konto eller trycka "Deploy" åt dig. Du gör så här:

## Vanligast: Railway är kopplat till GitHub

1. **Spara kod** i Cursor (filer sparade).
2. **Commit + push** till den branch Railway använder (ofta `main`):
   ```bash
   cd /sökväg/till/Gislegrillen_
   git add -A
   git status    # kolla att .env INTE följer med (den ska vara ignorerad)
   git commit -m "Webhook auth m.m."
   git push
   ```
3. Öppna **railway.app** → ditt projekt → **Deployments**.  
   När push landat startar en **ny build** automatiskt.

## Om du inte använder GitHub med Railway

- I **Railway** → din service → **Deployments** → **Redeploy** (eller ladda upp / koppla repo enligt deras guide).

## Köra servern lokalt (inte samma som Railway)

Fel du såg: `zsh: command not found: main.py`  
Rätt kommando i projektmappen:

```bash
python3 main.py
```

(`main.py` är en fil, inte ett kommando – Python måste starta den.)

## Efter deploy: webhook-secret

Kör (skriver **inte** ut hemlighet i terminal om du undviker `--print-secret`):

```bash
python3 scripts/setup_webhook_auth.py --rotate
```

Öppna filen **`.webhook_auth_instructions.txt`** i projektet och följ stegen för Railway + Vapi.
