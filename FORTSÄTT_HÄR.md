# Gislegrillen – Fortsättning för ny chatt

**Läs PROJECT_CONTEXT.md först** – då har du full projektkontext.

---

## Vad vi fixat (tidigare sessioner)

1. **Vapi toolCalls** – Vapi skickar `toolCalls` (inte bara toolCallList). Stöd lagt till.
2. **Dubbla notiser** – Deduplicering av tool-anrop (samma anrop i toolCalls + toolCallList).
3. **Order-id** – Slump-suffix så att inte två ordrar får samma id.

---

## Driftnotering

**Köksnotiser:** Backend skickar inte längre push till mobil. Ordrar syns via **Supabase/Lovable**, **dashboard** (`/dashboard`) och **köksbong i Railway-loggar**. Vid SMS-fel eller circuit breaker loggas `[ALERT]` i loggarna.

---

## Snabbstart (för ny chatt)

```
Läs PROJECT_CONTEXT.md och FORTSÄTT_HÄR.md. Gislegrillen röstbeställningssystem.
Backend: FastAPI, Vapi webhook, Supabase, valfritt Vonage SMS.
```

---

## Viktiga filer

- `main.py` – Backend
- `system_prompt.md` – Vapi system prompt
- `.env` – API-nycklar
- `orders.json` – Beställningar
