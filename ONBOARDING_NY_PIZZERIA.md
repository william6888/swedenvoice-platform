# Onboarda en ny pizzeria – körschema

Hela plattformen är multi-tenant: varje pizzeria får en egen UUID i `restaurants`,
en egen meny i `menus`, egen SMS-branding (namn + kontaktnummer), egen Vapi-assistent
och egen rad i `tenant_health`. Ingenting delas mellan pizzerior – fel-UUID-fallback
är avstängd för alla utom default-tenanten, så en order kan aldrig hamna i fel kök.

## Snabbvägen (rekommenderad)

Förbered en menyfil i samma format som `menu.json` (kategorier → listor med
`{"id": <unikt heltal>, "name": "...", "aliases": [...], "description": "..."}`)
och kör:

```bash
python3 scripts/onboard_pizzeria.py \
    --external-id PizzeriaRoma_01 \
    --name "Pizzeria Roma" \
    --contact-phone +46701234567 \
    --menu-file menu_pizzeria_roma.json \
    --create-vapi-assistant
```

Skriptet gör allt maskinellt i rätt ordning:

1. **Backend/Supabase** – `POST /admin/tenants/onboard`: skapar `restaurants`-raden
   (egen UUID), sparar menyn i `menus`, öppnar `tenant_health`. Idempotent:
   finns tenanten redan uppdateras bara menyn.
2. **Vapi** – klonar Gislegrillen-assistenten: samma röst/modell/inställningar men
   med pizzerians namn, en system-prompt genererad från menyfilen (rätt ID-karta)
   och en egen `place_order`-tool vars server-URL pekar på
   `.../vapi/webhook?rest_id=PizzeriaRoma_01` med `X-Webhook-Secret`-headern.
3. **Preflight** – `GET /admin/tenants/PizzeriaRoma_01/preflight` verifierar att
   restaurang, meny, branding, intake-status, webhook-secret och SMS-gateway är gröna.

## Två manuella steg (går inte via API)

1. **Telefonnummer:** i Vapi-dashboarden → Phone Numbers → koppla pizzerians nummer
   till den nya assistenten. Granska samtidigt den genererade system-prompten
   (särskilt rätternas namn/uttal) innan go-live.
2. **Lovable/KDS:** skapa en inloggningsanvändare i Supabase Auth och koppla den:

```sql
insert into public.restaurant_members (auth_user_id, restaurant_id)
values (
  (select id from auth.users where email = 'pizzeriaroma@dinplattform.se'),
  '<restaurant_uuid från onboarding-svaret>'
);
```

RLS gör resten – kontot ser bara sin egen restaurangs ordrar.

## Verifiera go-live

```bash
curl -s -H "X-Admin-Key: $ADMIN_SECRET" \
  "https://web-production-a9a48.up.railway.app/admin/tenants/PizzeriaRoma_01/preflight" | python3 -m json.tool
```

`"ready": true` = klart. Ring ett testsamtal, kontrollera att ordern får rätt
`restaurant_uuid` i Supabase och att kundens SMS visar pizzerians namn och nummer.

## Meny-ändringar i drift (ingen deploy)

```bash
curl -s -X POST "https://web-production-a9a48.up.railway.app/admin/menu/upload?rest_id=PizzeriaRoma_01" \
  -H "X-Admin-Key: $ADMIN_SECRET" -H "Content-Type: application/json" \
  --data-binary @menu_pizzeria_roma.json
```

Cachen invalideras automatiskt; ändringen är live inom sekunder. Kom ihåg att
uppdatera ID-kartan i tenantens Vapi-prompt om artikel-id:n ändras.

## Isoleringsgarantier (varför inget kan blandas ihop)

| Risk | Skydd |
| --- | --- |
| Order hamnar i fel kök | UUID slås alltid upp per `rest_id`; env-fallback endast för default-tenant |
| Fel meny används | Meny läses per `restaurant_uuid` ur `menus`; preflight blockerar tyst fallback |
| Fel namn/nummer i kund-SMS | Branding per tenant från `restaurants` |
| En tenant sänker en annan | Circuit breaker + token bucket är per `rest_id`; paus i `tenant_health` är per tenant |
| Kök ser annans ordrar | RLS: `restaurant_members`-scopade policies, anon-läsning borttagen |
