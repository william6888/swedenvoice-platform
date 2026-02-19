# Så sätter du ADMIN_SECRET (Fas 1 admin-endpoint)

## Vad det är
`ADMIN_SECRET` skyddar `POST /admin/tenants/{rest_id}/invalidate`. Endast anrop med rätt nyckel får rensa cache.

---

## 1. Lokalt (din dator) – filen `.env`

1. Öppna (eller skapa) filen **`.env`** i projektroten:  
   **`/Users/williamlarsson/Gislegrillen_/.env`**

2. Lägg till en rad (välj ett eget, hemligt lösenord):
   ```env
   ADMIN_SECRET=mitt_hemliga_admin_lösenord_123
   ```
   Använd **inte** "DITT_ADMIN_SECRET" – det var bara ett exempel. Välj något som bara du känner till.

3. Spara filen. **Starta om servern** (stoppa med Ctrl+C och kör `uvicorn main:app` igen) så laddas den nya variabeln.

4. Testa:
   ```bash
   curl -X POST "http://localhost:8000/admin/tenants/Gislegrillen_01/invalidate" \
     -H "X-Admin-Key: mitt_hemliga_admin_lösenord_123"
   ```
   Förväntat svar: `{"ok":true,"message":"Tenant caches invalidated","rest_id":"Gislegrillen_01"}`

Om du får **`{"detail":"Not Found"}`** betyder det att servern inte har den nya routen – se nedan under "Not Found".

---

## 2. På Railway (produktion)

1. Gå till **https://railway.app** och logga in.
2. Öppna ditt projekt → välj **appen** (den som hostar Gislegrillen/SwedenVoice).
3. Klicka på **Variables** (eller **Settings** → **Variables**).
4. Klicka **+ New Variable** (eller **Add Variable**).
5. Namn: **`ADMIN_SECRET`**  
   Värde: samma hemliga sträng som lokalt (t.ex. `mitt_hemliga_admin_lösenord_123`).
6. Spara. Railway startar om appen automatiskt.

7. Testa mot produktion (ersätt URL och nyckel):
   ```bash
   curl -X POST "https://web-production-a9a48.up.railway.app/admin/tenants/Gislegrillen_01/invalidate" \
     -H "X-Admin-Key: mitt_hemliga_admin_lösenord_123"
   ```

---

## Alternativ: nyckel i URL (query)

Du kan skicka nyckeln som query-parameter i stället för header:
```bash
curl -X POST "http://localhost:8000/admin/tenants/Gislegrillen_01/invalidate?admin_key=mitt_hemliga_admin_lösenord_123"
```

---

## "Not Found" när du anropar `/admin/tenants/...`

Det betyder att den **kod som körs** inte innehåller Fas 1-routen. Gör så här:

1. **Lokalt:** Stoppa servern (Ctrl+C). Kör om från projektmappen. Du behöver inte `uvicorn` i terminalen – använd **ett** av:
   ```bash
   cd /Users/williamlarsson/Gislegrillen_
   python3 main.py
   ```
   eller (med automatisk omladdning vid filändringar):
   ```bash
   python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```
   Om du inte har pushat Fas 1-koden till din branch än, gör det först (eller se till att `main.py` innehåller `@app.post("/admin/tenants/{rest_id}/invalidate")`).

2. **Railway:** Efter att du pushat koden med admin-routen deployar Railway om. Vänta tills deployen är klar och testa igen.

---

## Säkerhet

- Committa **aldrig** `.env` (den ska vara i `.gitignore`).
- Dela inte `ADMIN_SECRET` i chatten eller i repo. Den som har den kan rensa tenant-cache.
