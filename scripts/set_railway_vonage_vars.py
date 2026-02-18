#!/usr/bin/env python3
"""
Sätt Vonage-miljövariabler i Railway via API.
Kräver RAILWAY_TOKEN (Account token från https://railway.com/account/tokens)

Kör: RAILWAY_TOKEN=xxx python scripts/set_railway_vonage_vars.py
"""
import os
import sys
import json
import urllib.request

ENDPOINT = "https://backboard.railway.com/graphql/v2"
def get_vars():
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    return {
        "VONAGE_API_KEY": os.environ.get("VONAGE_API_KEY", ""),
        "VONAGE_API_SECRET": os.environ.get("VONAGE_API_SECRET", ""),
        "VONAGE_FROM_NUMBER": os.environ.get("VONAGE_FROM_NUMBER", ""),
    }

def gql(query: str, token: str, vars_: dict = None) -> dict:
    data = {"query": query}
    if vars_:
        data["variables"] = vars_
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(data).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def main():
    token = os.environ.get("RAILWAY_TOKEN")
    if not token:
        print("❌ Sätt RAILWAY_TOKEN (Account token från https://railway.com/account/tokens)")
        sys.exit(1)

    # Hämta projekt via workspaces
    q = """
    query {
      me {
        workspaces {
          edges {
            node {
              id
              teams {
                edges {
                  node {
                    id
                    projects {
                      edges {
                        node {
                          id
                          name
                          environments {
                            edges {
                              node {
                                id
                                name
                                services {
                                  edges {
                                    node {
                                      id
                                      name
                                    }
                                  }
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    try:
        resp = gql(q, token)
    except Exception as e:
        print(f"❌ API-fel: {e}")
        sys.exit(1)

    if "errors" in resp:
        print(f"❌ GraphQL-fel: {resp['errors']}")
        sys.exit(1)

    # Navigera workspaces -> teams -> projects
    data = resp.get("data", {}).get("me", {})
    ws_edges = data.get("workspaces", {}).get("edges", [])
    proj_id = env_id = service_id = None
    proj_name = env_name = "?"

    for ws in ws_edges:
        teams = ws.get("node", {}).get("teams", {}).get("edges", [])
        for te in teams:
            projs = te.get("node", {}).get("projects", {}).get("edges", [])
            for pe in projs:
                proj = pe.get("node", {})
                proj_id = proj.get("id")
                proj_name = proj.get("name", "?")
                env_edges = proj.get("environments", {}).get("edges", [])
                if env_edges:
                    env = env_edges[0].get("node", {})
                    env_id = env.get("id")
                    env_name = env.get("name", "?")
                    svc_edges = env.get("services", {}).get("edges", [])
                    if svc_edges:
                        service_id = svc_edges[0].get("node", {}).get("id")
                if proj_id and env_id:
                    break
            if proj_id:
                break
        if proj_id:
            break

    if not proj_id or not env_id:
        print("❌ Inga projekt/environments hittade. Kontrollera RAILWAY_TOKEN.")
        sys.exit(1)

    print(f"Projekt: {proj_name}, Env: {env_name}" + (f", Service-ID: {service_id[:8]}..." if service_id else " (shared)"))

    VARS = get_vars()
    if not all(VARS.values()):
        print("❌ Vonage-variabler saknas i .env (VONAGE_API_KEY, VONAGE_API_SECRET, VONAGE_FROM_NUMBER)")
        sys.exit(1)

    # variableCollectionUpsert
    upsert = """
    mutation VariableCollectionUpsert($input: VariableCollectionUpsertInput!) {
      variableCollectionUpsert(input: $input)
    }
    """
    input_ = {
        "projectId": proj_id,
        "environmentId": env_id,
        "variables": VARS,
    }
    if service_id:
        input_["serviceId"] = service_id

    try:
        r = gql(upsert, token, {"input": input_})
    except Exception as e:
        print(f"❌ Upsert-fel: {e}")
        sys.exit(1)

    if "errors" in r:
        print(f"❌ GraphQL-fel: {r['errors']}")
        sys.exit(1)

    print("✅ Vonage-variabler satta i Railway")
    for k in VARS:
        print(f"   {k}=***")

if __name__ == "__main__":
    main()
