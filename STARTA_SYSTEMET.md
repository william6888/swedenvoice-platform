# 🍕 Starta Gislegrillen Order System - Steg för Steg

## ✅ Vad du redan har klart:

1. ✅ Groq API-nyckel konfigurerad
2. ✅ Pushover notifikationer konfigurerade
3. ✅ Alla filer och kod på plats
4. ✅ `.env` fil skapad med dina nycklar

## 📋 Vad som återstår att göra:

### Steg 1: Skaffa Vapi API-nyckel (VIKTIGT!)

Systemet kan INTE ta emot röstsamtal utan denna nyckel.

**Så här gör du:**

1. Gå till: https://vapi.ai
2. Klicka på "Sign Up" (eller "Get Started")
3. Skapa ett konto (gratis att börja)
4. När du är inloggad, gå till: **Dashboard → API Keys**
5. Klicka på "Create New API Key"
6. Kopiera nyckeln (ser ut ungefär så: `sk_live_...` eller liknande)
7. Kör detta kommando för att lägga till nyckeln:

```bash
# Byt ut YOUR_VAPI_KEY_HERE med din riktiga nyckel
sed -i 's/VAPI_API_KEY=$/VAPI_API_KEY=YOUR_VAPI_KEY_HERE/' .env
```

**ELLER** öppna `.env` filen manuellt och lägg till din Vapi-nyckel på första raden där det står `VAPI_API_KEY=`

---

### Steg 2: Installera Python-paket

```bash
pip install -r requirements.txt
```

Om du får felmeddelanden, prova:
```bash
pip3 install -r requirements.txt
```

---

### Steg 3: Testa systemet lokalt

```bash
# Starta servern
python main.py
```

Du ska se:
```
============================================================
         🍕 GISLEGRILLEN VOICE AI ORDER SYSTEM 🍕
============================================================
FastAPI Server Starting...
Host: 0.0.0.0
Port: 8000
Dashboard: http://localhost:8000/dashboard
============================================================

✅ Server ready to accept orders!
```

**Öppna webbläsaren:** http://localhost:8000/dashboard

Du ska nu se köksdashboarden!

---

### Steg 4: Deploya till Railway (för Vapi)

Vapi behöver kunna nå din server från internet. **Deploya till Railway** enligt RAILWAY_GUIDE.md.

Du får en stabil URL som t.ex.:
```
https://gislegrillen-production.up.railway.app
```

---

### Steg 5: Konfigurera Vapi Assistant

Nu ska vi skapa din röst-AI på Vapi:

#### A) Logga in på Vapi Dashboard

1. Gå till: https://vapi.ai/dashboard
2. Klicka på **"Create Assistant"**

#### B) Grundinställningar

- **Name:** Gislegrillen Beställningsassistent
- **First Message:** "Hej, Gislegrillen! Vad får det lov att vara?"

#### C) Modell-inställningar

Scrolla ner till **"Model"**:

- **Provider:** Groq
- **Model:** llama-3.1-70b-versatile
- **Temperature:** 0.7
- **Max Tokens:** 500

#### D) System Prompt

1. Öppna filen `system_prompt.md` (i detta projekt)
2. Kopiera **HELA** innehållet
3. Klistra in det i **"System Prompt"** fältet på Vapi

#### E) Röst-inställningar

Scrolla till **"Voice"**:

- **Provider:** ElevenLabs (eller Play.ht)
- **Language:** Swedish (sv-SE)
- **Voice:** Välj en professionell, vänlig svensk röst
  - Förslag: "Adam" eller "Antoni" (ElevenLabs)
- **Speed:** 1.0
- **Stability:** 0.5

#### F) Lägg till Tool (VIKTIGT!)

Scrolla till **"Tools"** → Klicka **"Add Tool"** → Välj **"Server Tool"**

Fyll i:

**Tool Name:** `place_order`

**URL:** `https://DIN-RAILWAY-URL.up.railway.app/vapi/webhook`

**Method:** POST

**Description:**
```
Place a customer order with items, quantities, and special requests. Call this when the customer has confirmed their order.
```

**Parameters Schema:** (Kopiera exakt!)
```json
{
  "type": "object",
  "properties": {
    "items": {
      "type": "array",
      "description": "List of ordered items with ID, name, and quantity",
      "items": {
        "type": "object",
        "properties": {
          "id": {
            "type": "integer",
            "description": "Menu item ID number"
          },
          "name": {
            "type": "string",
            "description": "Name of the menu item"
          },
          "quantity": {
            "type": "integer",
            "description": "Number of items ordered"
          }
        },
        "required": ["id", "name", "quantity"]
      }
    },
    "special_requests": {
      "type": "string",
      "description": "Any special requests from the customer (e.g., 'ingen lök', 'extra ost')"
    }
  },
  "required": ["items"]
}
```

Klicka **"Save Tool"**

#### G) Spara Assistant

Klicka **"Save"** eller **"Create Assistant"**

---

### Steg 6: Skaffa ett telefonnummer

1. I Vapi Dashboard, gå till **"Phone Numbers"**
2. Klicka **"Buy Phone Number"**
3. Välj **Sverige (+46)** om möjligt (eller annat land)
4. Köp numret (kostar lite pengar)
5. Koppla numret till din **"Gislegrillen Beställningsassistent"**

---

### Steg 7: Testa systemet!

#### Testa med telefon:

1. Ring ditt Vapi-nummer
2. AI ska säga: "Hej, Gislegrillen! Vad får det lov att vara?"
3. Beställ något: "Hej, jag vill ha en Hawaii och en Coca-Cola"
4. Följ konversationen
5. När du bekräftar beställningen ska AI kalla på `place_order`

#### Vad du ska se:

**I terminalen (där servern körs):**
```
============================================================
                    🔔 KÖKS-BONG! 🔔
============================================================
ORDER ID: ORD-20260208153045
TID: 2026-02-08 15:30:45
------------------------------------------------------------
ARTIKLAR:
  [1x] Hawaii (98 kr)
  [1x] Coca-Cola 33cl (25 kr)
------------------------------------------------------------
TOTALT: 123 kr
============================================================
```

**På din telefon (Pushover-appen):**
Du får en notifikation med beställningen!

**På dashboarden:**
http://localhost:8000/dashboard - Beställningen syns där!

---

## 🔧 Felsökning

### Problem: "WARNING: VAPI_API_KEY not configured!"
**Lösning:** Du har inte lagt till Vapi-nyckeln i `.env` filen. Se Steg 1.

### Problem: "Connection refused" eller "Cannot connect to server"
**Lösning:** 
1. Kontrollera att servern körs (`python main.py`)
2. Kontrollera att Railway-deploy är aktiv
3. Uppdatera Server URL i Vapi med din Railway-URL

### Problem: AI pratar engelska istället för svenska
**Lösning:**
1. Kontrollera att du kopierade HELA `system_prompt.md` till Vapi
2. Kontrollera att rösten är inställd på Swedish (sv-SE)

### Problem: Ingen notifikation från Pushover
**Lösning:**
1. Ladda ner Pushover-appen på din telefon
2. Logga in med ditt Pushover-konto
3. Kontrollera att nycklarna i `.env` är korrekta

### Problem: Orders visas inte på dashboarden
**Lösning:**
1. Kontrollera att `orders.json` finns och är skrivbar
2. Öppna webbläsarens konsol (F12) och kolla efter fel
3. Verifiera att servern körs

---

## 📱 Produktionsdrift (valfritt)

När du är redo att köra systemet permanent:

### Alternativ 1: Deploy till en server

**Rekommenderade tjänster:**
- **DigitalOcean App Platform** (enklast)
- **Heroku**
- **Railway.app**
- **AWS EC2** (mer avancerat)

### Alternativ 2: Kör på en lokal server

1. Skaffa en dator som kan köra 24/7
2. Installera systemet där
3. Använd en router med portforwarding (port 8000)
4. Deploya till Railway (rekommenderat, se RAILWAY_GUIDE.md)

---

## ✅ Checklista innan du går live:

- [ ] Vapi API-nyckel tillagd i `.env`
- [ ] Alla Python-paket installerade
- [ ] Servern startar utan fel
- [ ] Dashboard är tillgänglig på http://localhost:8000/dashboard
- [ ] Railway-deploy aktiv
- [ ] Vapi Assistant är skapad och konfigurerad
- [ ] `system_prompt.md` är kopierad till Vapi
- [ ] `place_order` tool är konfigurerad med rätt URL
- [ ] Telefonnummer är köpt och kopplat
- [ ] Testsamtal gjort och fungerar
- [ ] Beställning syns i terminalen
- [ ] Beställning syns på dashboarden
- [ ] Pushover-notifikation funkar

---

## 🎯 Snabbkommandon

```bash
# Starta servern
python main.py

# Testa systemet
python test_system.py

# Deploy till internet
# Se RAILWAY_GUIDE.md

# Se alla beställningar
curl http://localhost:8000/orders | python -m json.tool

# Se menyn
curl http://localhost:8000/menu | python -m json.tool

# Manuellt testa en beställning
curl -X POST http://localhost:8000/place_order \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"id": 4, "name": "Hawaii", "quantity": 1}
    ],
    "special_requests": "Ingen lök"
  }'
```

---

## 📞 Exempel på testsamtal

**Du ringer Vapi-numret:**

```
AI: "Hej, Gislegrillen! Vad får det lov att vara?"

Du: "Hej, jag vill beställa en Hawaii."

AI: "En Hawaii, okej. Vill du ha något att dricka till det?"

Du: "Ja, en Coca-Cola."

AI: "Perfekt! Så det blir en Hawaii och en Coca-Cola. Stämmer det?"

Du: "Ja, det stämmer."

AI: "Tack för din beställning! Den är klar om 15 minuter. Välkommen! Hejdå!"
```

→ Beställningen dyker upp i terminalen, på dashboarden och i Pushover!

---

## 🆘 Behöver du hjälp?

1. Kör testerna: `python test_system.py`
2. Kolla serverlogs i terminalen
3. Kontrollera Vapi logs i deras dashboard
4. Öppna browser console (F12) på dashboarden

---

**Lycka till! 🍕📞**

Systemet är redo att ta emot beställningar så fort du har lagt till Vapi API-nyckeln!
