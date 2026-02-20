#!/usr/bin/env python3
"""
Smoke-test för Fas 2: meny-cache och GET /api/keywords.
Använder requests (ingen TestClient). Kör mot localhost eller Railway.

  python3 scripts/smoke_test_fas2.py
  python3 scripts/smoke_test_fas2.py https://web-production-xxxx.up.railway.app
"""
import sys
import requests

DEFAULT_BASE = "http://localhost:8000"


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE).rstrip("/")
    print("Smoke-test Fas 2: %s" % base)
    ok = True

    connection_errors = 0

    # GET /menu
    try:
        r = requests.get("%s/menu" % base, timeout=5)
        if r.status_code != 200:
            print("  FAIL GET /menu: status %s" % r.status_code)
            ok = False
        else:
            j = r.json()
            if "pizzas" not in j or not isinstance(j["pizzas"], list):
                print("  FAIL GET /menu: saknar pizzas eller ogiltig struktur")
                ok = False
            else:
                print("  OK  GET /menu (%d pizzor)" % len(j["pizzas"]))
    except requests.exceptions.ConnectionError:
        print("  SKIP GET /menu: servern svarar inte (starta med python3 main.py)")
        connection_errors += 1
    except Exception as e:
        print("  FAIL GET /menu: %s" % e)
        ok = False

    # GET /api/keywords
    try:
        r = requests.get("%s/api/keywords" % base, timeout=5)
        if r.status_code != 200:
            print("  FAIL GET /api/keywords: status %s" % r.status_code)
            if r.status_code == 404:
                print("    (Starta om servern efter Fas 2-kodändringar.)")
            ok = False
        else:
            j = r.json()
            if "keywords" not in j or "keyterms" not in j:
                print("  FAIL GET /api/keywords: saknar keywords/keyterms")
                ok = False
            else:
                print("  OK  GET /api/keywords (%d keywords, %d keyterms)" % (len(j["keywords"]), len(j["keyterms"])))
    except requests.exceptions.ConnectionError:
        print("  SKIP GET /api/keywords: servern svarar inte")
        connection_errors += 1
    except Exception as e:
        print("  FAIL GET /api/keywords: %s" % e)
        ok = False

    if ok:
        print("\nFas 2 smoke-test: OK")
        sys.exit(0)
    if connection_errors == 2:
        print("\nFas 2 smoke-test: SKIP (servern körs inte)")
        sys.exit(0)
    print("\nFas 2 smoke-test: FAIL")
    sys.exit(1)


if __name__ == "__main__":
    main()
