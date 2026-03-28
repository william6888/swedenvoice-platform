# Checklista – lösa problemen (gör i denna ordning)

## Vad du löser med detta

1. **Ny kod** (webhook-skydd m.m.) kommer upp på **Railway**.  
2. **Säkerhet:** Bara Vapi (med rätt header) kan anropa `/place_order` och `/vapi/webhook` när hemligheten är satt.

---

## Steg 1 – Spara och skicka kod till GitHub

1. Spara alla filer i Cursor (**Cmd+S** / File → Save All).  
2. Öppna **Terminal** i Cursor (ny flik om `python3 main.py` redan kör → **Ctrl+C** först, eller ny terminal).  
3. Gå till projektmappen:
   ```bash
   cd ~/Gislegrillen_
   ```
   (Byt sökväg om din mapp heter annat.)

4. Kolla att **`.env` inte ska committas:**
   ```bash
   git status
   ```
   - Om `.env` visas som **ny fil** som ska in i commit → **lägg inte till den**. (Den ska vara i `.gitignore`.)

5. Committa och pusha:
   ```bash
   git add -A
   git commit -m "Webhook auth och uppdateringar"
   git push
   ```
   Om `git push` klagar på inloggning → logga in mot GitHub som du brukar (Cursor/terminal kan fråga).

---

## Steg 2 – Vänta på Railway

1. Öppna **https://railway.app** → ditt projekt → **Deployments**.  
2. Vänta tills senaste deploy är **grön / lyckad**.  
   (Om Railway inte är kopplat till GitHub måste du koppla repo eller trycka **Redeploy** enligt deras guide.)

---

## Steg 3 – Hemlighet för Vapi ↔ Railway (samma värde på två ställen)

1. I terminalen, i projektmappen:
   ```bash
   python3 scripts/setup_webhook_auth.py --rotate
   ```
   (`--rotate` = ny nyckel. Har du **aldrig** satt något i Vapi/Railway än kan du använda `python3 scripts/setup_webhook_auth.py` utan `--rotate`.)

2. Öppna filen **`.webhook_auth_instructions.txt`** i projektet (den syns i filträdet; den **committas inte**).  
   Där står **exakt** vad du ska klistra in.

3. **Railway:**  
   Variables → **New** → Name: `WEBHOOK_SHARED_SECRET` → Value: (från filen) → Spara → **Redeploy** / Restart service.

4. **Vapi:**  
   Där **Server URL** mot Railway finns (assistant / telefonnummer / tool) → **HTTP Headers** →  
   Name: `X-Webhook-Secret`  
   Value: **samma** som i Railway, tecken för tecken.

5. **Lägg aldrig** denna hemlighet i AI-chat eller skärmdump.

---

## Steg 4 – Testa

1. Ring / testa en beställning som vanligt.  
2. Om **401 Unauthorized** → Vapi och Railway har **olika** värde, eller Railway inte omstartad efter variabel.

---

## Snabb felsökning

| Problem | Åtgärd |
|--------|--------|
| `command not found: main.py` | Kör `python3 main.py` |
| Inga ordrar efter auth | Jämför `X-Webhook-Secret` i Vapi med `WEBHOOK_SHARED_SECRET` i Railway |
| Vill stänga av auth tillfälligt | Ta bort variabeln `WEBHOOK_SHARED_SECRET` i Railway → redeploy (endast om du förstår risken) |

---

Mer läsning: `DEPLOY_ENKEL.md`, `ENKEL_WEBHOOK_AUTH.md`.
