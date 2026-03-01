#!/usr/bin/env python3
"""Test: place_order med name+quantity (utan id). Verifierar att backend löser namn till id."""
import sys
import requests

BASE = "http://localhost:8000"
if len(sys.argv) > 1:
    BASE = sys.argv[1].rstrip("/")

URL = "%s/vapi/webhook?rest_id=Gislegrillen_01" % BASE

# Items med BARA name och quantity (ingen id) – backend ska lösa till id
payload = {
    "message": {
        "type": "tool-calls",
        "toolCallList": [{
            "id": "test-name-001",
            "parameters": {
                "items": [
                    {"name": "Vesuvio", "quantity": 1},
                    {"name": "Hawaii", "quantity": 2}
                ],
                "special_requests": "extra sås på Vesuvio",
                "customer_name": "Test Namn"
            }
        }],
        "call": {"customer": {"number": "0700000000"}}
    }
}

def main():
    print("📤 Webhook med items (name + quantity, inget id) →", URL)
    try:
        r = requests.post(URL, json=payload, timeout=15)
        print("Status:", r.status_code)
        print("Svar:", r.text[:600])
        if r.status_code == 200 and "success" in r.text.lower() and "error" not in r.text.lower():
            print("\n✅ Name→id fungerar. Order sparad med Vesuvio + Hawaii.")
        else:
            print("\n⚠️  Kolla svar (servern måste köra med senaste main.py).")
    except requests.exceptions.ConnectionError:
        print("❌ Servern svarar inte. Starta med: python3 main.py")
    except Exception as e:
        print("❌", e)

if __name__ == "__main__":
    main()
