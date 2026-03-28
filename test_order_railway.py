#!/usr/bin/env python3
"""
Testa webhook mot RAILWAY (inte localhost).
Uppdatera RAILWAY_URL nedan om du har annan URL.
"""
import json
import os
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

RAILWAY_URL = "https://web-production-a9a48.up.railway.app"
# Tenant-blind: lägg till ?rest_id=Gislegrillen_01 (eller annat external_id) för multi-tenant-test
URL = f"{RAILWAY_URL}/vapi/webhook"

payload = {
    "message": {
        "type": "tool-calls",
        "toolCallList": [{
            "id": "test-railway-001",
            "parameters": {
                "items": [{"id": 1, "quantity": 1}],
                "special_requests": "",
                "customer_name": "Test Railway"
            }
        }],
        "call": {
            "assistantId": "Gislegrillen_01",
            "customer": {"number": "0701234567"}
        }
    }
}

def main():
    print("📤 Skickar till RAILWAY:", URL)
    print("   Om lyckat: Pushover, SMS, Supabase + Lovable")
    print()
    secret = (os.environ.get("WEBHOOK_SHARED_SECRET") or "").strip()
    headers = {}
    if secret:
        headers["X-Webhook-Secret"] = secret
        print("   (använder WEBHOOK_SHARED_SECRET från miljö)")
    try:
        r = requests.post(URL, json=payload, headers=headers, timeout=15)
        print(f"Status: {r.status_code}")
        print(f"Svar: {r.text[:600]}")
        if r.status_code == 200:
            if '"results"' in r.text:
                print("\n✅ Order processad! Kolla Pushover, Supabase, Lovable.")
            else:
                print("\n⚠️  Svar OK men inga results – tool-calls parsades kanske inte.")
        else:
            print("\n❌ Felstatus – kolla att Railway körs.")
    except Exception as e:
        print(f"❌ Fel: {e}")

if __name__ == "__main__":
    main()
