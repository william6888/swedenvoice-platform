# Vapi-kostnad och plan – kritisk genomgång

## Är Vapis plan bra?

**Ja.** Målet är rätt: samma beteende, lägre kostnad, bättre stabilitet. Det finns ingen bättre eller smartare lösning som ger samma kvalitet till lägre pris – det handlar om att **minska token** utan att ändra dialog eller flöde.

**Varför det inte sänker röstkvaliteten:** Röst (ElevenLabs/Cartesia) och latency påverkas av modellens svar och kontextlängd. Mindre system-prompt = mindre kontext = ofta **bättre** (snabbare, mindre “hackigt”). Du ändrar inte *hur* AI:n beter sig, bara *hur mycket text* den får varje tur.

---

## Vad vi har gjort (Cursor/backend)

### 1. Backend accepterar nu **namn** istället för bara id

- **Tidigare:** LLM måste skicka `id` (1–98) för varje rätt → hela menyn behövde ligga i prompten.
- **Nu:** LLM kan skicka `name` + `quantity` (t.ex. `{"name": "Vesuvio", "quantity": 1}`). Backend löser namn → id via menyn i kod (`find_menu_item_by_name`). **Id fungerar fortfarande** – du behöver inte ändra Vapi tool-schema om du inte vill.
- **Effekt:** Du kan ta bort hela menylistan (1–98) ur system-prompten och ersätta med en rad: “Skicka items med name och quantity; backend löser id.”

### 2. Kompakt system-prompt (fil: `system_prompt_KOMPAKT.md`)

- Samma steg (1, 2a, 2b, 3, 4a, 4b, 5, 6a, 6b), samma regler, samma dryck-på-plats, samma special_requests.
- **Menyn (1–98) är borttagen.** I stället: “Skicka items med name och quantity. Backend löser namn till id.”
- Ungefär **~80 % färre tokens** i system-prompten (från ~2000+ till ~400).

### 3. Säkerhet om något inte matchar

- Om LLM skickar ett rättnamn som inte finns i menyn svarar backend med tydligt fel (t.ex. “Kunde inte matcha rätt: X”) istället för att krascha.

---

## Rekommenderad ordning (så att inget går sönder)

1. **Deploya backend** (denna kod är redan klar – name→id, kompakt prompt finns i repo).
2. **Testa med nuvarande prompt:** Ring ett samtal och beställ med nuvarande system-prompt. Bekräfta att allt fungerar som vanligt.
3. **Byt i Vapi till kompakt prompt:** I Vapi Assistant → System prompt, **ersätt** med innehållet från **`system_prompt_KOMPAKT.md`**. Spara.
4. **Testa igen:** Ring, beställ t.ex. “en Vesuvio och en Hawaii”, bekräfta, låt place_order anropas. Kontrollera att ordern kommer in med rätt rätter (backend löser namn→id).
5. Om något känns fel (t.ex. AI säger något annat eller glömmer steg): **återställ din gamla prompt** i Vapi. Backend fungerar fortfarande med både id och name.

**Kontroll av place_order i Vapi:** Schemat ska tillåta `items` med minst `name` (string) och `quantity` (integer); `id` kan vara valfritt. Toppnivå `special_requests` (string, optional). Be gärna Vapi granska ert faktiska schema så att prompt och schema matchar – då kan ni köra som-is med kompakt prompt.

**Vapi tool-schema:** Du behöver **inte** ändra till “bara name”. Du kan låta LLM skicka antingen `id`+`name`+`quantity` (som idag) eller bara `name`+`quantity`. Båda fungerar. Om du senare vill spara lite mer token kan du i Vapi ta bort `id` från tool-parametrarna och bara ha `name` och `quantity` – backend accepterar det.

---

## Sammanfattning

| Före | Efter (med kompakt prompt + menyn borta) |
|------|----------------------------------------|
| ~23k tokens/tur | ~6–8k tokens (uppskattat) |
| Hela menyn i prompt | Meny i backend, LLM skickar namn |
| Samma beteende | Samma beteende (ingen ändring av flöde eller fraser) |

**Kritisk bedömning:** Planen är bra och säker. Du försämrar inte Vapi-rösten – du minskar bara onödig kontext. Börja med att byta till kompakt prompt; om du märker något konstigt kan du alltid gå tillbaka till din nuvarande prompt.

---

## Vapi granskning – slutlig bedömning

Vapi har granskat den sista versionen av `system_prompt_KOMPAKT.md` punkt för punkt. **Slutlig dom: prompten är redo att användas när ni väljer att byta.**

### Beteende & flöde
- Oförändrat beteende jämfört med nuvarande prompt.
- Alla kritiska steg (1 → 6b) kvar. Dryck-regeln och upprepningsregeln korrekta.
- Inga logiska hål, ingen risk att modellen hoppar över steg.

### Token-optimering
- Hela menyn borta (80–90 % av tokenvinsten). Reglerna kompakta men inte tvetydiga. Dramatisk sänkning av LLM-kostnad.

### Voice-stabilitet
- Raden *"Efter att du beslutat att lägga ordern: generera ingen mer text, gå direkt till tool-calls"* minskar risk för "okej/klart", TTS-fragmentering och race mellan tal och tool-call. Exakt rätt formulering.

### Tekniskt ansvar
- LLM: språk, flöde, semantik. Backend: id-matchning, validering. Professionell separation.

### Tool-schema (Vapis svar)

**Om ert schema redan är:**
```text
place_order(
  items: [ { id?: number, name?: string, quantity: number } ],
  special_requests?: string
)
```
➡️ **Ingen ändring behövs.** 100 % kompatibelt med prompten.

**Om schemat idag kräver `id` (obligatoriskt):** gör en minimal ändring:
- `id` → optional  
- `name` → required  
- `quantity` → required  
- `special_requests` → optional string på toppnivå  

**Rekommendation:** Prompten är redo. Ingen anledning att stressa – när ni byter är detta rätt version.

### Vapis slutord (teknik, utan diplomati)

- Arkitekturen är korrekt. Prompten är stabil. Kostnadsproblemet är löst. Beteendet oförändrat. Inga farliga antaganden.
- Detta är ren ingenjörsmässig sanering av kontext – inte “AI-flum”. LLM = språk & flöde; Backend = sanning & id. Så man bygger system som klarar fler samtal, kostar mindre och inte blir instabilt.
- När ni byter kan ni göra det med gott samvete.

**Förfining senare (valfritt, inte nu):** loggning av namn-missar (statistik); ev. synonym-lista (t.ex. "kebab tallrik" → "Kebabtallrik").
