# Enkel webhook-auth (3 steg)

Koden är redan på plats i `main.py`. Du behöver bara **en hemlighet** på två ställen.

## 1. Kör skriptet (på din dator, i projektmappen)

```bash
python3 scripts/setup_webhook_auth.py
```

För **ny** hemlighet (t.ex. om gammal kan ha synts i chat):

```bash
python3 scripts/setup_webhook_auth.py --rotate
```

- Uppdaterar `.env`.
- Skriver **allt du behöver** (inkl. hemlighet) till **`.webhook_auth_instructions.txt`** — filen **committas inte** (gitignore). **Öppna den filen** och kopiera till Railway/Vapi — **lägg inte hemligheten i AI-chat.**

Valfritt: `--print-secret` skriver också ut i terminal (undvik i Cursor om chatten loggar terminal).

## 2. Railway

Öppna **`.webhook_auth_instructions.txt`** → kopiera **Name** och **Value** till **Variables** → **Redeploy**.

## 3. Vapi

Samma fil → lägg header **`X-Webhook-Secret`** med **samma Value** där server-URL:en mot Railway är konfigurerad.

## Deploy av kod

Se **`DEPLOY_ENKEL.md`** (Git push → Railway bygger).

---

**Om något slutar fungera:** Vapi och Railway måste ha **identiskt** värde. Tom `WEBHOOK_SHARED_SECRET` på Railway = auth avstängd (som före).

Mer detalj: `WEBHOOK_AUTH_SETUP.md`.
