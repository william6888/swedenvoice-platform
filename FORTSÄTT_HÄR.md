# Gislegrillen – Fortsättning för ny chatt

**Läs PROJECT_CONTEXT.md först** – då har du full projektkontext.

---

## Vad vi fixat (denna session)

1. **Vapi toolCalls** – Vapi skickar `toolCalls` (inte bara toolCallList). Stöd lagt till.
2. **Dubbla notiser** – Deduplicering av tool-anrop (samma anrop i toolCalls + toolCallList).
3. **Order-id** – Slump-suffix så att inte två ordrar får samma id.
4. **Pushover retry** – Ett extra försök vid misslyckat anrop.

---

## Kvarvarande problem

**Pushover-notiser fungerar inte alltid** – Ibland får användaren notis, ibland inte.

Möjliga orsaker att undersöka:
- Både Tool URL (`/place_order`) OCH webhook (`/vapi/webhook`) konfigurerade i Vapi → kan ge dubbel/bristande hantering.
- Ska endast **en** URL användas: Messaging Server URL = `https://DIN-RAILWAY-URL/vapi/webhook`.
- Pushover-app beteende vid många notiser.
- I terminalen: sök efter `⚠️ Pushover FAILED` eller `❌ Pushover-fel`.

---

## Snabbstart (för ny chatt)

```
Läs PROJECT_CONTEXT.md och FORTSÄTT_HÄR.md. Gislegrillen röstbeställningssystem. 
Pushover-notiser kommer inte alltid fram. Vi har lagt till toolCalls-stöd, deduplicering, retry. 
Hjälp mig felsöka varför notiser uteblir.
```

---

## Viktiga filer

- `main.py` – Backend
- `system_prompt.md` – Vapi system prompt
- `.env` – API-nycklar
- `orders.json` – Beställningar
