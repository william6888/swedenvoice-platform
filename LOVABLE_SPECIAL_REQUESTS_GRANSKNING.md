# Granskning: Lovables ärende om specialönskemål

## Vad Lovable sa (kort)

- Specialönskemål ("extra sås", "utan lök") fångas av Vapi men sparas inte i databasen.
- `raw_transcript` är tomt, det finns ingen `special_instructions`-kolumn.
- Föreslagen lösning: lägg till `special_instructions` i Supabase, fyll från backend, spara även `raw_transcript`.

## Granskning – vad som stämde

- **Korrekt:** Backend sparade inte `special_requests` i Supabase. Vi hade redan `order.special_requests` i minnet och i Pushover/SMS, men `_insert_order_to_supabase` skrev aldrig med det till `orders`-tabellen.
- **Korrekt:** `raw_transcript` skickades aldrig till Supabase – vi anropade `_insert_order_to_supabase` utan `raw_transcript`, så det blev alltid tomt.
- **Korrekt:** Kolumnen `special_instructions` fanns inte i `orders` – den behövde läggas till med `ALTER TABLE`.

## Vad som var onödigt eller oklart

- **Per-item notes:** Lovable nämnde att man "alternativt" kan spara per item med `notes`. Vi har redan `OrderItem.special_requests` i backend; det är nu inkluderat i `items`-JSON som `notes` så att KDS kan visa perrättsanteckningar om ni vill.
- **Raw transcript:** Vapi skickar inte alltid hela transkriptet i samma webhook-anrop som tool-calls. Vi försöker nu hämta det från `message.transcript`, `message.content`, `call.transcript` och `body.transcript`. Om Vapi placerar det någon annanstans (t.ex. endast i ett senare event) kommer `raw_transcript` fortfarande att vara tomt tills vi anpassar extraktionen till er payload.

## Implementerat (Cursor)

1. **Supabase:** Du måste köra `ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS special_instructions text;` i extern Supabase (se `SUPABASE_ADD_SPECIAL_INSTRUCTIONS.sql`).
2. **Backend:**  
   - `_insert_order_to_supabase` skickar nu `special_instructions` (från `order.special_requests`) och inkluderar `notes` per item i `items`-JSON.  
   - `raw_transcript` hämtas från webhook-body via `_get_raw_transcript_from_webhook(body)` och skickas med till `_insert_order_to_supabase` i båda webhook-flödena (place_order med tool-calls och /vapi/webhook).
3. **Lovable:** Ingen kodändring – KDS visar redan `special_instructions` på orderkorten när fältet finns i databasen.

## Möjliga framtida problem

- **Vapi skickar inte transkript i tool-call-payload:** Då blir `raw_transcript` tomt. Om ni vill ha det måste ni antingen använda ett Vapi-event som innehåller hela transkriptet och anropa backend därifrån, eller kontrollera Vapis dokumentation för var transkriptet skickas och uppdatera `_get_raw_transcript_from_webhook` därefter.
- **Kolumnen saknas i Supabase:** Om ni glömmer att köra `ALTER TABLE` kommer insert att ge fel (kolumnen finns inte). Kör migreringen en gång i er externa databas.
- **Storlek:** Långa transkript eller special_instructions kan bli stora. `text` i Postgres hanterar det; om ni senare vill begränsa längd kan ni lägga till CHECK eller trunkera i backend.

## Sammanfattning

Lovables beskrivning var korrekt; lösningen (kolumn + backend fyller fälten) är rätt. Vi har implementerat det och lagt till per-item `notes` samt försök att fylla `raw_transcript` från webhook. Du behöver bara köra SQL-migreringen i Supabase en gång.
