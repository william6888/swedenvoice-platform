#!/usr/bin/env python3
"""
Test-skript: Simulerar en Vapi webhook (tool-calls) till /vapi-webhook.
Skickar en beställning: 1x Pizza ID 1, kund Test Testsson, tel 0701234567.
"""

import json
import requests

URL = "http://localhost:8000/vapi/webhook"

# Simulerad Vapi tool-calls payload
payload = {
    "message": {
        "type": "tool-calls",
        "toolCallList": [
            {
                "id": "test-order-001",
                "parameters": {
                    "items": [{"id": 1, "quantity": 1}],
                    "special_requests": "",
                    "customer_name": "Test Testsson"
                }
            }
        ],
        "call": {
            "assistantId": "Gislegrillen_01",
            "customer": {"number": "0701234567"}
        }
    }
}

def main():
    print("📤 Skickar test-webhook till", URL)
    print("   Order: 1x Pizza (ID 1)")
    print("   Kund: Test Testsson")
    print("   Telefon: 0701234567")
    print("   restaurant_id: Gislegrillen_01")
    print()
    try:
        r = requests.post(URL, json=payload, timeout=10)
        print(f"Status: {r.status_code}")
        print(f"Svar: {r.text[:500]}")
        if r.status_code == 200:
            print("\n✅ Test lyckades! Kolla orders.json, Supabase och Pushover.")
        else:
            print("\n⚠️  Fick felstatus – kolla att servern körs på port 8000")
    except requests.exceptions.ConnectionError:
        print("❌ Kunde inte ansluta. Starta servern först:")
        print("   python3 main.py")
    except Exception as e:
        print(f"❌ Fel: {e}")

if __name__ == "__main__":
    main()
