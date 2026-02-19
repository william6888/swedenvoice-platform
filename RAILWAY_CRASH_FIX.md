# Railway-crash – vad som ändrats

## Vad vi ändrat (denna fix)

1. **Ingen `from __future__ import annotations`** – vi använder nu explicita `typing.Tuple` och `typing.Dict` överallt där vi hade `tuple[...]` / `dict[...]`. Fungerar stabilt på Python 3.7, 3.8 och 3.11 (Railway kan ibland använda annan version än runtime.txt).

2. **`call_id` alltid str** – Vapi kan skicka `message.call.id` som tal; vi konverterar till `str()` innan användning som cache-nyckel så att det inte kraschar.

3. **Säker cache-skrivning** – `_cache_restaurant_for_call` skippar om `call_id` är tom och använder `str(call_id)` vid skriv.

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
