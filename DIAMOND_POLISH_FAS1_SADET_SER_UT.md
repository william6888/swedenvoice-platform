# Så ser Fas 1 (Bakgrunds-SMS) ut – steg för steg

**Till dig som chef:** Här beskrivs exakt vad som händer idag respektive när Fas 1 är klart, så att du ser skillnaden utan att behöva koda.

---

## Idag (innan Fas 1)

### Vad som händer när en kund beställer via telefonen

1. **Kunden säger beställningen** och AI:n (Vapi) tolkar och skickar till vår webhook.
2. **Vår server:**
   - Sparar ordern (orders.json + Supabase).
   - Skickar köksnotis till er (Pushover).
   - **Väntar** på Vonage (SMS) – anropar Vonage och **står stilla** tills Vonage svarar (ofta 0,5–2 sekunder).
   - Skickar sedan svaret tillbaka till Vapi: "Order bekräftad, order_id …".
3. **Vapi** får alltså svaret **först när både order, Pushover och SMS är klara**. Under tiden (0,5–2 sek) "väntar" samtalet i praktiken på oss.
4. **Kunden** får SMS någon sekund efter att de lagt beställningen; upplevelsen kan kännas lite dröjande om Vonage är långsam.

**Kort sagt:** Allt görs i en rad. SMS-blocket gör att Vapi får svar lite senare än nödvändigt.

---

## Efter Fas 1 (när det är klart)

### Samma scenario – men med bakgrunds-SMS

1. **Kunden beställer** – samma som idag. Vapi skickar till vår webhook.
2. **Vår server:**
   - Sparar ordern (orders.json + Supabase) – **oförändrat**.
   - Skickar köksnotis till er (Pushover) – **oförändrat**.
   - **Registrerar** att "SMS ska skickas" (lägger det som ett litet uppdrag i bakgrunden).
   - **Skickar direkt** tillbaka till Vapi: "Order bekräftad, order_id …" **utan att vänta på Vonage**.
3. **Vapi** får svaret **nästan direkt** (typ direkt efter sparande + Pushover). Ingen väntan på Vonage.
4. **Samtidigt, i bakgrunden** (på vår server, efter att vi redan svarat Vapi):
   - Uppdraget kör: skicka SMS via Vonage till kunden.
   - Om det **lyckas:** kunden får SMS som vanligt. Du ser inget extra.
   - Om det **misslyckas** (t.ex. Vonage nere, fel nummer): du får en **Pushover-varning** till dig med typ:  
     *"[ALERT] SMS misslyckades – order_id ORD-…, rest_id Gislegrillen_01, fel: …"*  
     Då vet du att just den ordern inte fick bekräftelse-SMS och kan följa upp (t.ex. ringa kunden).

**Kort sagt:** Order och köksnotis är oförändrade. Skillnaden är att vi **inte väntar** på SMS innan vi svarar Vapi, och att du **får en tydlig varning** om SMS inte gick att skicka.

---

## Konkret exempel – sekund för sekund

### Idag (före)

| Sekund | Vad som händer |
|--------|-----------------|
| 0 | Vapi skickar beställning till vår webhook. |
| 0–0,1 | Vi sparar order, skickar Pushover. |
| 0,1–1,5 | Vi anropar Vonage för SMS och **väntar** på svar. |
| 1,5 | Vonage svarar. Vi skickar svar tillbaka till Vapi. |
| 1,5+ | Vapi får "order bekräftad" och kan avsluta/bekräfta för kunden. Kunden får SMS runt samma tid. |

**Du märker:** Om Vonage är långsam (t.ex. 2 s) så är det 2 s extra innan Vapi får svar och samtalet kan kännas lite "laggigt".

---

### Efter Fas 1

| Sekund | Vad som händer |
|--------|-----------------|
| 0 | Vapi skickar beställning till vår webhook. |
| 0–0,1 | Vi sparar order, skickar Pushover. |
| 0,1 | Vi lägger "skicka SMS till denna kund" som bakgrundsuppdrag och **skickar direkt** svar till Vapi: "Order bekräftad, order_id …". |
| 0,1+ | **Vapi får svaret direkt** och kan bekräfta för kunden utan att vänta på Vonage. |
| 0,1–1,5 | **I bakgrunden** (samtidigt som Vapi redan har fått svar): vår server skickar SMS via Vonage. Kunden får SMS ungefär som idag, bara att Vapi inte har väntat på det. |
| Om SMS **misslyckas** | Du får en Pushover med text typ: *"[ALERT] SMS misslyckades – order_id ORD-20260219…, rest_id Gislegrillen_01, fel: …"* så att du kan följa upp. |

**Du märker:** Samtalet väntar inte på Vonage; det "flyter" bättre. Kunden får fortfarande SMS (om Vonage fungerar), och du får en tydlig varning om det inte gör det.

---

## Vad du ser som användare (pizzeria/chef)

- **I er app / kök:** Ingen skillnad. Order kommer in som nu, Pushover till köket fungerar som vanligt.
- **På er telefon (Pushover):**  
  - Vanliga ordernotiser: oförändrade.  
  - **Nytt:** Om en SMS inte kunde skickas får du en **extra notis** med "[ALERT] SMS misslyckades …" och order_id + eventuellt felmeddelande, så du vet vilken order som inte fick bekräftelse-SMS.
- **I Vapi / samtalet:** AI:n får bekräftelse snabbare och kan avsluta/upprepa order utan att vänta på Vonage – mindre känsla av "lagg".

---

## Sammanfattning i en mening

**Idag:** Vi väntar på SMS (Vonage) innan vi svarar Vapi → lite onödigt lagg.  
**Efter Fas 1:** Vi svarar Vapi direkt och skickar SMS i bakgrunden; om SMS misslyckas får du en tydlig Pushover-varning så att du kan följa upp manuellt.

Confidence-gating skippar vi som du bestämt; all fokus på keyword-boosting (Speechmatics) och denna bakgrunds-SMS-förbättring.
