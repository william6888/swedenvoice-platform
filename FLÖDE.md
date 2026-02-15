# Så här går beställningsflödet till

## 1. Vad är "Context used"?

**Context used** = hur mycket av chatthistoriken som AI:n har tillgång till. När den når ~97–100% blir chatten för stor, då **komprimeras/sammanfattas** den automatiskt. Du behöver inte starta ny chatt – Cursor sparar en sammanfattning så att vi kan fortsätta. Men detaljer kan tappas bort.

---

## 2. Flödet steg för steg

```
Du ringer Vapi-nummer
        ↓
Vapi svarar (AI röst)
        ↓
Du säger: "Jag vill ha en Vesuvio"
        ↓
Vapi → transkriberar röst till text
        ↓
Groq LLM (AI) får texten → förstår beställning
        ↓
AI svarar: "Så en Vesuvio. Något att dricka? Stämmer det?"
        ↓
Du säger: "Ja" eller "Stämmer"
        ↓
AI anropar place_order-verktyget
        ↓
Vapi skickar HTTP POST till din server
        ↓
  ┌─────────────────────────────────────────────────────┐
  │  RAILWAY (moln) eller localhost                      │
  │  https://gislegrillen.railway.app                    │
  └─────────────────────────────────────────────────────┘
        ↓
Din FastAPI-server (main.py) tar emot anropet på:
  • /place_order  (om Tool URL är satt i Vapi)
  • /vapi/webhook (om Messaging Server URL är satt, event "tool-calls")
        ↓
main.py: _process_place_order()
  → sparar i orders.json
  → skriver köksbong i terminalen
  → anropar send_pushover_notification()
        ↓
Pushover API (internet) → push till din mobil
```

---

## 3. Viktigt: När skickas place_order?

Enligt system_prompt.md:

> "Vid **ja** → anropa place_order"

Alltså: AI:n anropar place_order **först när du har bekräftat**. Om du bara säger "Vesuvio" och inte svarar "ja" på bekräftelsen, anropas place_order inte.

---

## 4. Varför ingen Pushover-notis?

| Steg | Vad kolla | Om det inte fungerar |
|------|-----------|-----------------------|
| A | Når request vår server? | Titta i **terminalen** – ser du `📥 place_order received` eller `📞 Vapi Webhook Event: tool-calls`? |
| B | Annars | Fel URL i Vapi (Tool URL / Messaging Server URL) – använd Railway-URL. |
| C | Sparas ordern? | Kolla `orders.json` – läggs nya ordrar till? |
| D | Pushover konfigurerad? | Kör: `curl http://localhost:8000/test_pushover` – får du notis? |
| E | Ser du "Pushover notification sent" i terminal? | Då når anropet Pushover. Annars: kolla .env (PUSHOVER_USER_KEY, PUSHOVER_API_TOKEN). |

---

## 5. Snabbtest

1. **Testa Pushover direkt:**
   ```bash
   curl http://localhost:8000/test_pushover
   ```
   Får du notis på mobilen? I så fall är Pushover OK.

2. **Testa place_order direkt (simulera Vapi):**
   ```bash
   curl -X POST http://localhost:8000/place_order \
     -H "Content-Type: application/json" \
     -d '{"items":[{"id":2,"name":"Vesuvio","quantity":1}],"special_requests":null}'
   ```
   Ser du köksbong i terminalen + Pushover-notis? Då fungerar backend + Pushover.

3. **Ring och säg exakt:**
   - "Hej, jag vill ha en Vesuvio"
   - AI: "Så en Vesuvio. Stämmer det?"
   - Du: "Ja"

   Om AI:n inte frågar bekräftelse eller du inte säger "ja" – då anropas place_order inte.
