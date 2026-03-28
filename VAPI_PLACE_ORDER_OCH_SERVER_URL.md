# Vapi: `place_order` Server URL (Railway) – rekommendationer & risker

## Ska `place_order` peka på Railway?

**Ja.** Sätt **Server URL** för verktyget `place_order` till din publika Railway-URL **med rätt path**:

```text
https://<din-service>.up.railway.app/place_order
```

- **HTTPS** (Railway ger det automatiskt).
- **Path måste vara** `/place_order` – inte bara domänen (annars 404).
- För **multi-tenant**: lägg ofta query, t.ex. `?rest_id=Gislegrillen_01` (samma som i Supabase `external_id`), om ni använder det i Vapi/webhook.

Ersätt **aldrig** med `https://api.example.com/function` – det är bara exempel i UI.

---

## Tycker vi om Vapis varningar? (kort)

| Punkt | Bedömning |
|-------|-----------|
| Fel path / 404 | **Relevant.** Använd full URL inkl. `/place_order`. |
| Fel JSON till Vapi | **Relevant.** Er `main.py` returnerar `{"results":[...]}` med `name`, `toolCallId`, `result` för Vapi-format – bra. |
| Timeout 20 s | **Relevant.** Supabase + Pushover + bakgrund-SMS ska normalt vara under 20 s; vid problem: höj timeout i Vapi eller optimera. |
| Railway kallstart | **Relevant.** Första anrop efter viloläge kan vara långsamt; överväg alltid-på / health-ping eller Railway-plan som inte sover. |
| Auth headers | **Relevant om ni lägger till auth.** Idag: "No authentication" i Vapi matchar backend (ingen obligatorisk header för `place_order`). |
| Assistant-level `server.url` | **Medelrisk.** Om allt går till en URL måste den svara **200** snabbt på många eventtyper. Er `/vapi/webhook` hanterar bl.a. `end-of-call-report` och okända events med 200 – **okej** om ni sätter webhook dit. |
| Tool + assistant URL | **Tänk igenom:** Tool med egen URL → anrop går till **`/place_order`**, inte automatiskt till `/vapi/webhook` (se kommentar i `main.py`). Undvik dubbel logik för samma order. |
| SMS | **Korrekt från Vapi:** Railway-URL fixar inte carrier-SMS; SMS styrs av Vonage + `VONAGE_*` i Railway. |

---

## Ytterligare risk (viktig): idempotency / dubbel order

Om Vapi eller LLM **retry:ar** samma tool-call kan er backend skapa **två ordrar** om ni inte deduplicerar (t.ex. på `toolCallId` + call-id inom tidsfönster).

**Status i kod:** ingen uttrycklig idempotency-key i `place_order` – värt att implementera senare om ni ser dubletter i loggar/DB.

---

## Rekommenderad uppdelning

1. **`place_order` → Tool Server URL**  
   `https://...railway.app/place_order` (+ `?rest_id=...` om ni behöver).

2. **Webhook för samtal (valfritt)**  
   I Vapi **Phone Number** eller **Assistant** webhook:  
   `https://...railway.app/vapi/webhook`  
   (samma host som Railway – bra för loggar och `call_id`-cache till tenant).

3. **Async** på verktyget i Vapi: följ Vapis dokumentation – säkerställ att er server fortfarande returnerar det svar Vapi förväntar sig för er konfiguration.

---

## Snabb checklista

- [ ] `place_order` URL = Railway + `/place_order` (inte example.com).
- [ ] `rest_id` i query om flera restauranger / tenant lookup kräver det.
- [ ] Railway **Variables** (Vonage, Supabase, etc.) uppdaterade efter deploy.
- [ ] **`WEBHOOK_SHARED_SECRET`**: sätt i Railway + samma värde som Vapi-header (`X-Webhook-Secret` eller Bearer). Se **WEBHOOK_AUTH_SETUP.md**. Tom variabel = ingen auth (bakåtkompatibelt).
- [ ] Testa med Vapis **Test** på verktyget eller ett riktigt samtal.
- [ ] Vid dubbel-order i loggar: planera idempotency (`toolCallId`).
