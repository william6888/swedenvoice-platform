# Vilka filer behövs – och vad gör debug-URL:erna?

## Vad gör de två URL:erna?

### 1. `https://web-production-a9a48.up.railway.app/debug-tenant?rest_id=Gislegrillen_01`
- **Syfte:** Kontrollera att **tenant-lookup** fungerar (multi-tenant).
- **Gör:** Läser `rest_id` från query (t.ex. `Gislegrillen_01`), slår upp i Supabase-tabellen `restaurants` och returnerar `restaurant_id`, `restaurant_uuid` och `lookup_ok`.
- **När du använder den:** När du vill verifiera att backend hittar rätt restaurang utifrån `?rest_id=...` (samma som i Vapi Server URL). Påverkar inte produktion – bara läsning.

### 2. `https://web-production-a9a48.up.railway.app/debug-call-cache`
- **Syfte:** Visa hur många **samtal** som finns i den tillfälliga cachen (call_id → restaurang).
- **Gör:** Returnerar `cache_size` (antal poster) och `entries_within_ttl` (antal som fortfarande är inom 1 timmes TTL).
- **När du använder den:** Vid felsökning av multi-tenant (t.ex. "ser place_order rätt restaurang?"). Påverkar inte produktion – bara läsning.

Båda är **endast för kontroll/felsökning**. Du behöver inte anropa dem för att systemet ska fungera; de påverkar inte ordrar eller kunddata.

---

## Behövs det så många filer?

**Nej.** Många filer skapades under felsökning eller som “klistra in till Gemini/Supabase/Lovable”. Appen **kör bara** på: `main.py`, `requirements.txt`, `menu.json`, `system_prompt.md`, `Procfile`, `runtime.txt`, och (vid behov) `orders.json`, `start_server.sh`, `.env` / `.env.template`. Resten är dokumentation, tester eller SQL du kört en gång.

---

## Kategorier

### ✅ Ska finnas kvar (app eller projekt behöver dem)
| Fil | Varför |
|-----|--------|
| `main.py` | Backend – all logik. |
| `requirements.txt` | Pip-beroenden (Railway m.m.). |
| `menu.json` | Meny – används av appen. |
| `system_prompt.md` | Används av API/system. |
| `Procfile` | Säg åt Railway hur appen startar. |
| `runtime.txt` | Python-version för Railway. |
| `.env` / `.env.template` | Miljövariabler (template som mall). |
| `orders.json` | Används om ni sparar ordrar lokalt (kan vara tom/valfri). |
| `README.md` | Vanlig projektbeskrivning. |

### 📌 Bra att ha (en eller några guider)
| Fil | Varför |
|-----|--------|
| `VAD_SKA_JAG_GÖRA.md` | Steg-för-steg: vad du ska göra, vad som ska till Supabase/Lovable. |
| `PROJECT_CONTEXT.md` | Sammanfattning av projektet (referens för Cursor/Gemini). |
| `RAILWAY_GUIDE.md` | Hur man deployar till Railway. |
| `VAPI_SETUP_GUIDE.md` | Hur Vapi kopplas. |

Du behöver **inte** en ny fil varje gång du skickar något till Gemini eller Supabase. Det räcker med **en** (t.ex. `VAD_SKA_JAG_GÖRA.md` eller `PROJECT_CONTEXT.md`) som du uppdaterar med “det jag ska klistra till Gemini/Supabase” när det behövs.

### ❌ Kan tas bort utan att något går sönder (en-gångs-/felsökningsdokument)
Dessa påverkar **inte** körning, deploy eller databas. De är anteckningar, felsökningssteg eller texter du redan klistrat in någonstans.

| Fil | Typ |
|-----|-----|
| `CURSOR_SVAR_TILL_GEMINI_PLAN.md` | Cursors svar till Gemini – redan använt. |
| `SAMMANFATTNING_TILL_GEMINI.md` | Sammanfattning till Gemini – redan använt. |
| `DEBUG_KEDJA.md` | Felsökning. |
| `FELSOK_NU.md` | Felsökning. |
| `FRAGA_SUPABASE_SENASTE_ORDER.md` | Fråga till Supabase – en gång. |
| `KEDJA_DIAGNOS.md` | Felsökning. |
| `KLISTRA_IN_TILL_LOVABLE.md` | Text till Lovable – en gång. |
| `LOVABLE_PROBLEM.md` | Felsökning Lovable. |
| `LOVABLE_SETUP.md` | Setup – kan ligga i en guide istället. |
| `LOVABLE_VISAR_INGET_FELSOK.md` | Felsökning. |
| `MULTI_TENANCY_PLAN.md` | Plan – nu genomförd. |
| `NUVARANDE_STATUS.md` | Status – inaktuell. |
| `PROBLEM_IDENTIFIERAT.md` | Felsökning. |
| `PROJECT_SUMMARY.txt` | Duplicerar ofta README/PROJECT_CONTEXT. |
| `QUICKSTART.md` / `SNABBSTART.txt` | Kan slås ihop med README eller VAD_SKA_JAG_GÖRA. |
| `RAILWAY_CRASH_FIX.md` | Förklaring av crash-fix – referens, inte kod. |
| `STARTA_SYSTEMET.md` | Kan ingå i README eller en guide. |
| `SUPABASE_ADVISOR_SVAR.md` | Svar från Supabase – en gång. |
| `SUPABASE_DEBUG_SQL.md` | Felsökning. |
| `SUPABASE_PROBLEM_OCH_PLAN.md` | Plan – genomförd. |
| `TILL_SUPABASE_VERIFIERA.md` | Verifiering – en gång. |
| `VAR_FELET_LIGGER.md` | Felsökning. |
| `VERIFIERA_OCH_RISKER.md` | Verifiering/risk – kan samlas i en fil. |
| `KOMPLETT_GUIDE.md` | Kan duplicera innehåll i andra guider. |
| `FORTSÄTT_HÄR.md` | Anteckning. |
| `FLÖDE.md` | Flödesbeskrivning – kan ligga i PROJECT_CONTEXT. |
| `supabase_migration_plan.md` | Plan – migration redan gjord. |

### SQL-filer (referens – påverkar inte körning)
- `supabase_create_orders.sql`, `supabase_fas_b_c.sql`, `supabase_policies_orders.sql`, `supabase_rls_orders.sql`, `supabase_safe_phase1.sql`, `supabase_verifiera_status.sql`  
- Används när du kör/körde kommandon i Supabase. Behövs inte för att appen ska starta. Du kan ta bort dem om du inte längre behöver referensen, eller lägga dem i en mapp t.ex. `supabase/` om du vill hålla kvar dem.

### Tester (valfria)
- `test_order_railway.py`, `test_order.py`, `test_system.py`, `test_vapi_formats.sh`  
- Användbara för att köra tester; krävs inte för deploy. Säkert att ta bort om du inte använder dem.

### Övrigt
- `system_prompt_fast.md` – används bara om någon kod uttryckligen läser den; annars kan den tas bort om du inte använder “fast”-varianten.

---

## Kort svar

1. **Debug-URL:erna**  
   - **debug-tenant:** Kontrollerar att `?rest_id=...` ger rätt `restaurant_id`/`restaurant_uuid` från Supabase.  
   - **debug-call-cache:** Visar antal poster i call_id → restaurang-cachen.  
   Båda är bara för kontroll; de behövs inte för att beställningar eller något annat ska fungera.

2. **Filer**  
   Du behöver **inte** skapa en ny fil varje gång du skickar något till Gemini/Supabase. Det räcker med en eller några guider (t.ex. `VAD_SKA_JAG_GÖRA.md` + `PROJECT_CONTEXT.md`) som du uppdaterar.

3. **Helt onödiga att ha kvar**  
   Alla filer i listan under “Kan tas bort utan att något går sönder” påverkar **ingen** körning eller deploy. Om du tar bort dem händer inget med appen, Railway eller Supabase. Du kan tryggt ta bort dem om du vill rensa projektet; behåll gärna de du vill ha som minne/referens.
