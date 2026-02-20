#!/usr/bin/env python3
"""
Test: Webhook med explicit rest_id (query). För att verifiera multi-pizzeria-flödet.
Kräver att servern körs. Valfritt: skapa menu_Pizzeria_B.json för egen meny.

  python3 test_order_with_rest_id.py
  python3 test_order_with_rest_id.py https://web-production-xxxx.up.railway.app
"""
import sys
import requests

BASE = "http://localhost:8000"
if len(sys.argv) > 1:
    BASE = sys.argv[1].rstrip("/")

# rest_id som query – så backend använder rätt tenant (och eventuellt menu_<rest_id>.json)
URL = "%s/vapi/webhook?rest_id=Gislegrillen_01" % BASE

payload = {
    "message": {
        "type": "tool-calls",
        "toolCallList": [{
            "id": "test-rest-id-001",
            "parameters": {
                "items": [{"id": 1, "quantity": 1}],
                "special_requests": "",
                "customer_name": "Test RestId"
            }
        }],
        "call": {"customer": {"number": "0700000000"}}
    }
}

def main():
    print("📤 Webhook med ?rest_id=Gislegrillen_01 →", URL)
    try:
        r = requests.post(URL, json=payload, timeout=10)
        print("Status:", r.status_code)
        print("Svar:", r.text[:400])
        if r.status_code == 200 and "success" in r.text.lower():
            print("\n✅ OK – rest_id används för meny/cache/Supabase.")
        else:
            print("\n⚠️  Kontrollera svar eller starta servern.")
    except requests.exceptions.ConnectionError:
        print("❌ Servern svarar inte. Starta med: python3 main.py")
    except Exception as e:
        print("❌", e)

if __name__ == "__main__":
    main()
