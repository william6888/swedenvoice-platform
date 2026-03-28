# WEBHOOK_SHARED_SECRET – säkra Vapi → Railway

## Varför

Utan hemlighet kan vem som helst som känner till URL:en skicka falska `POST` till `/place_order` eller `/vapi/webhook`.

## Säkraste rollout (minst risk)

1. **Deploya** ny kod till Railway **utan** att sätta `WEBHOOK_SHARED_SECRET` ännu → inget ändras i beteende.
2. Generera en **lång slumpsträng** (t.ex. 32+ tecken). Sätt i **Railway → Variables**: `WEBHOOK_SHARED_SECRET=<strängen>`.
3. I **Vapi** (samma Server URL som idag), lägg till **en** av följande:
   - **HTTP Headers** → `X-Webhook-Secret` = samma sträng som i Railway, **eller**
   - **Credential / Bearer** så att `Authorization: Bearer <samma sträng>` skickas (beroende på hur du skapar credential i Vapi).
4. **Redeploy** Railway om variabeln var ny.
5. Testa ett **riktigt samtal** eller `test_order_railway.py` lokalt med `WEBHOOK_SHARED_SECRET` i `.env`.

## Vad som *inte* skyddas (medvetet)

- `GET /menu`, `GET /dashboard`, `POST /update_order_status` (köksdashboard) – oförändrat så du slipper ändra `index.html`.
- Admin-endpoints använder fortfarande `X-Admin-Key` / `ADMIN_SECRET` som tidigare.

## Om något slutar fungera

- **401 Unauthorized** från Railway → Vapi skickar fel eller saknar header, eller Railway har annat värde än Vapi.
- **Tom** `WEBHOOK_SHARED_SECRET` i Railway → auth är avstängd (som före ändringen).

## Rotera hemlighet

1. Sätt nytt värde i Railway **och** uppdatera Vapi **i samma fönster** (eller acceptera kort avbrott).
