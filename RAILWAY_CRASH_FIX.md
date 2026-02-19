# Railway-crash – undersökning och fix

## Orsak (identifierad genom jämförelse mot senaste fungerande commit)

**Senaste fungerande:** `2969543` – "Add /debug-supabase and Supabase skip log".

**Jämförelse:** Diff mot första multi-tenant-commit (`b487dd1`) visade två saker:

### 1. Indentationsfel i `/place_order` (huvudorsaken till crash)

I multi-tenant-commiten ändrades indentation av flera rader i `place_order`-endpointen:
- Rader som skulle ligga **inuti** `try:`-blocket (restaurant_id, customer_name, _insert_order_to_supabase, results.append) fick **för få mellanslag** (20 i stället för 24).
- Då hamnade de **utanför** try-blocket och `except Exception as e:` matchade inte längre sin `try:`.
- Det ger **SyntaxError / IndentationError** när Python **laddar modulen** (vid `uvicorn main:app`). Servern startar därför aldrig – därav "Crashed" direkt efter deploy.

**Åtgärd:** Indentation är återställd så att hela blocket (order, pushover, restaurant_id, customer_name, _insert_order_to_supabase, results.append, inner try/except för SMS) ligger inuti samma `try:`, och `except Exception as e:` har rätt indentation (24 mellanslag).

### 2. Type hints (sekundärt, om Railway kör Python 3.8)

- `dict[str, dict]` och `tuple[str, Optional[str]]` är ogiltiga i Python 3.8 vid utvärdering.
- Vi har bytt till `typing.Dict` och `typing.Tuple` så att det fungerar i 3.7/3.8 och 3.11.

### 3. call_id som dict-nyckel

- `call_id` från Vapi kan vara tal; vi gör `str()` så att det alltid är säkert som cache-nyckel.

## Connect to Browser (på bilden)

- **Vad det gör:** Öppnar appens URL (t.ex. din Railway-URL) i webbläsaren.
- **När det är crashed:** Du får bara fel/502 – tjänsten svarar inte. Då är det **inte** bra att förlita dig på det för att testa.
- **När det fungerar:** Då kan du använda det för att öppna t.ex. `/debug-tenant?rest_id=Gislegrillen_01` eller `/health` och verifiera att allt svarar.

## Efter push – gör så här

1. **Pusha** (commit med Tuple/Dict + call_id-str är redan gjord).
2. **Vänta** tills Railway visar grön deployment (1–2 min).
3. **Logs:** Om det fortfarande kraschar → Railway → **Logs** (eller View logs på senaste deployment). Kopiera felmeddelandet/traceback och felsök utifrån det.
4. **Testa:** När status är grön → öppna i webbläsare:  
   `https://web-production-a9a48.up.railway.app/health`  
   sedan  
   `https://web-production-a9a48.up.railway.app/debug-tenant?rest_id=Gislegrillen_01`  
   Kör sedan `python3 test_order_railway.py`.
