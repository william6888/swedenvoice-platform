"""
Gislegrillen Voice AI Order System
FastAPI backend for Vapi.ai voice order integration
"""

import base64
import hashlib
import json
import os
import re
import time
import menu_match
import order_integrity
import order_service
import ops_agent
import ops_worker
import confirmation
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
import uvicorn

# Load .env från samma mapp som main.py (så ADMIN_SECRET m.m. hittas oavsett arbetskatalog)
_env_path = Path(__file__).resolve().parent / ".env"
_load_ok = load_dotenv(dotenv_path=str(_env_path))
if not _load_ok:
    load_dotenv()
# Fallback: om ADMIN_SECRET fortfarande saknas (t.ex. dotenv-parsefel), läs raden direkt från .env
if not os.getenv("ADMIN_SECRET") and _env_path.exists():
    try:
        with open(_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ADMIN_SECRET="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        os.environ["ADMIN_SECRET"] = val
                    break
    except Exception:
        pass


def _clean_env_value(name: str, default: str = "") -> str:
    """Läs env-värde och ta bort whitespace som annars kan bryta strikt API-auth."""
    return (os.getenv(name, default) or default).strip()


# Configuration (måste vara före Supabase-init)
SUPABASE_URL = _clean_env_value("SUPABASE_URL")
SUPABASE_KEY = _clean_env_value("SUPABASE_KEY")
# Multi-tenancy: UUID för denna restaurang (från public.restaurants). Sätts när Supabase har restaurant_uuid.
RESTAURANT_UUID = _clean_env_value("RESTAURANT_UUID") or None

# Supabase client (optional – används för KDS/Lovable Dashboard)
_supabase_client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        key_preview = "eyJ... (JWT)" if SUPABASE_KEY.strip().startswith("eyJ") else "***"
        print(f"✅ Supabase client initialized (key: {key_preview})")
    except Exception as e:
        print(f"⚠️  Supabase init failed: {e}")

# Configuration
VAPI_API_KEY = _clean_env_value("VAPI_API_KEY")
VONAGE_API_KEY = _clean_env_value("VONAGE_API_KEY")
VONAGE_API_SECRET = _clean_env_value("VONAGE_API_SECRET")
VONAGE_FROM_NUMBER = _clean_env_value("VONAGE_FROM_NUMBER")
HOST = _clean_env_value("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
# Fas 1 Safety Net: admin-endpoint
ADMIN_SECRET = _clean_env_value("ADMIN_SECRET")
# Valfritt: delad hemlighet för Vapi → POST /place_order och /vapi/webhook. Om tom: ingen kontroll (bakåtkompatibelt).
# I Vapi: Custom header "X-Webhook-Secret: <samma värde>" ELLER Authorization: Bearer <samma värde>
WEBHOOK_SHARED_SECRET = _clean_env_value("WEBHOOK_SHARED_SECRET")
RESTAURANT_CONTACT_NUMBER = _clean_env_value("RESTAURANT_CONTACT_NUMBER", "+46760445700")
SMS_EXCLUDED_NUMBERS = _clean_env_value("SMS_EXCLUDED_NUMBERS")

# Fas 2: Kryptering av tenant-nycklar (restaurant_secrets)
ENCRYPTION_SECRET = _clean_env_value("ENCRYPTION_SECRET")
_fernet = None
if ENCRYPTION_SECRET:
    try:
        from cryptography.fernet import Fernet
        key = base64.urlsafe_b64encode(hashlib.sha256(ENCRYPTION_SECRET.encode()).digest())
        _fernet = Fernet(key)
    except Exception as e:
        print("⚠️  Fernet init failed (Fas 2 secrets disabled): %s" % e)

# File paths
BASE_DIR = Path(__file__).parent
MENU_FILE = BASE_DIR / "menu.json"
ORDERS_FILE = BASE_DIR / "orders.json"
SYSTEM_PROMPT_FILE = BASE_DIR / "system_prompt.md"

# Order integrity feature flags
# ORDER_REQUIRE_DB_COMMIT=true betyder att backend returnerar success:false
# om Supabase-commit misslyckas. I produktion ska denna vara true.
ORDER_REQUIRE_DB_COMMIT = (os.getenv("ORDER_REQUIRE_DB_COMMIT", "true") or "true").strip().lower() == "true"
# DASHBOARD_FROM_DB=true betyder att /orders och /update_order_status använder
# Supabase som primär källa istället för orders.json.
DASHBOARD_FROM_DB = (os.getenv("DASHBOARD_FROM_DB", "true") or "true").strip().lower() == "true"
# DEFAULT_DASHBOARD_REST_ID styr vilken tenant lokala /dashboard visar i utveckling.
DEFAULT_DASHBOARD_REST_ID = _clean_env_value("DEFAULT_DASHBOARD_REST_ID", "Gislegrillen_01")
# REQUIRE_DRAFT_TOKEN=true tvingar AI att gå via /draft_order innan /place_order.
# Default FALSE för bakåtkompatibilitet med befintlig Vapi-prompt: aktivera (env=true)
# först när din Vapi-assistant uppdaterats till draft-flödet i system_prompt.md.
# Ordergaranti-modulen är aktiv ändå (idempotency, validation, Supabase-commit).
REQUIRE_DRAFT_TOKEN = (os.getenv("REQUIRE_DRAFT_TOKEN", "false") or "false").strip().lower() == "true"
# OPS_AGENT_ENABLED=true startar ops-worker som in-process bakgrundstask.
# Detta ger autonom drift utan extern cron (Railway/GitHub Actions). Default ON.
OPS_AGENT_ENABLED = (os.getenv("OPS_AGENT_ENABLED", "true") or "true").strip().lower() == "true"
# OPS_AGENT_INTERVAL_SEC styr hur ofta ticken körs.
try:
    OPS_AGENT_INTERVAL_SEC = max(15, int(os.getenv("OPS_AGENT_INTERVAL_SEC", "90")))
except ValueError:
    OPS_AGENT_INTERVAL_SEC = 90

# Initialize FastAPI app
app = FastAPI(
    title="Gislegrillen Voice AI Order System",
    description="Production-ready order management system with Vapi.ai integration",
    version="1.0.0"
)

# CORS middleware for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_VAPI_PROTECTED_PATHS = frozenset({"/place_order", "/vapi/webhook", "/vapi-webhook"})


@app.middleware("http")
async def verify_vapi_webhook_secret(request: Request, call_next):
    """Om WEBHOOK_SHARED_SECRET är satt: kräv Bearer eller X-Webhook-Secret på Vapi-endpoints."""
    if request.method != "POST" or request.url.path not in _VAPI_PROTECTED_PATHS:
        return await call_next(request)
    if not WEBHOOK_SHARED_SECRET:
        return await call_next(request)
    auth = (request.headers.get("authorization") or "").strip()
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    header_secret = (request.headers.get("x-webhook-secret") or "").strip()
    if bearer == WEBHOOK_SHARED_SECRET or header_secret == WEBHOOK_SHARED_SECRET:
        return await call_next(request)
    return JSONResponse(
        content={"detail": "Unauthorized", "hint": "Set X-Webhook-Secret or Authorization: Bearer to match WEBHOOK_SHARED_SECRET"},
        status_code=401,
    )


@app.middleware("http")
async def log_post_path(request: Request, call_next):
    """Logga POST till place_order/webhook – spåra var tool-calls går."""
    if request.method == "POST" and request.url.path in ("/place_order", "/vapi/webhook", "/vapi-webhook"):
        print(f">>> INCOMING POST {request.url.path} <<<")
    return await call_next(request)

_OPS_BACKGROUND_TASK = None


async def _ops_background_loop():
    """
    Periodisk autonom ops-tick. Körs som in-process asyncio-task vid uppstart.
    Behöver ingen extern cron – ger självläkande drift även om Railway saknar
    schemaläggare. Tar inga tunga lås, så hot path är opåverkad.
    """
    import asyncio as _asyncio
    # Importera lazy så modulen kan starta även om ops_worker inte hittas.
    while True:
        try:
            await _asyncio.sleep(OPS_AGENT_INTERVAL_SEC)
            if not _supabase_client:
                continue
            # Kör synkrona tick i thread så vi inte blockerar event-loopen.
            await _asyncio.to_thread(
                ops_worker.run_tick,
                _supabase_client,
                sms_sender=_sms_sender_for_worker,
            )
        except _asyncio.CancelledError:
            print("ops_agent: background loop cancelled")
            raise
        except Exception as e:
            print(f"ops_agent: background tick error: {e}")


@app.on_event("startup")
async def startup_debug():
    """Verifiera Supabase och starta ops-agenten autonomt om aktiverad."""
    print(f"DEBUG VONAGE: VONAGE_API_KEY={'SET' if VONAGE_API_KEY else 'MISSING'}")
    print(f"DEBUG VONAGE: VONAGE_API_SECRET={'SET' if VONAGE_API_SECRET else 'MISSING'}")
    print(f"DEBUG VONAGE: VONAGE_FROM_NUMBER={'SET' if VONAGE_FROM_NUMBER else 'MISSING'}")
    print(f"Fas 1: POST /admin/tenants/{{rest_id}}/invalidate (ADMIN_SECRET={'SET' if ADMIN_SECRET else 'MISSING'})")
    print(f"WEBHOOK_SHARED_SECRET: {'SET (Vapi måste skicka header)' if WEBHOOK_SHARED_SECRET else 'NOT SET — /place_order och /vapi/webhook är öppna'}")
    print(f"REQUIRE_DRAFT_TOKEN: {REQUIRE_DRAFT_TOKEN} (Vapi MÅSTE anropa /draft_order innan /place_order när detta är true)")
    # Kontrollera att vi kan läsa restaurants (RLS kräver service_role; anon får 0 rader)
    if _supabase_client:
        try:
            r = _supabase_client.table("restaurants").select("id").limit(1).execute()
            if not (r.data and len(r.data) > 0):
                print("⚠️  Supabase restaurants returnerade 0 rader. Om du aktiverat RLS: sätt SUPABASE_KEY till service_role (inte anon) i Railway.")
        except Exception as e:
            print("⚠️  Supabase restaurants-check misslyckades: %s – kontrollera SUPABASE_KEY (använd service_role om RLS är på)" % e)

    if OPS_AGENT_ENABLED:
        import asyncio as _asyncio
        global _OPS_BACKGROUND_TASK
        _OPS_BACKGROUND_TASK = _asyncio.create_task(_ops_background_loop())
        print(f"✅ Ops-agent kör autonomt (intervall {OPS_AGENT_INTERVAL_SEC}s)")
    else:
        print("ℹ️  Ops-agent inaktiverad (OPS_AGENT_ENABLED=false). Använd POST /admin/ops/run manuellt.")


@app.on_event("shutdown")
async def shutdown_ops_agent():
    """Stäng ner ops-loopen rent vid shutdown."""
    if _OPS_BACKGROUND_TASK:
        _OPS_BACKGROUND_TASK.cancel()
        try:
            await _OPS_BACKGROUND_TASK
        except Exception:
            pass

# ==================== DATA MODELS ====================

class OrderItem(BaseModel):
    id: int
    name: str
    quantity: int = Field(ge=1, le=order_integrity.MAX_QUANTITY_PER_ITEM)
    price: Optional[float] = None
    special_requests: Optional[str] = None

    @field_validator("special_requests")
    @classmethod
    def _trim_sr(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        text = str(v).strip()
        if len(text) > order_integrity.MAX_SPECIAL_REQUEST_LEN:
            text = text[: order_integrity.MAX_SPECIAL_REQUEST_LEN].rstrip()
        return text

class PlaceOrderRequest(BaseModel):
    items: List[OrderItem] = Field(min_length=1, max_length=order_integrity.MAX_ITEMS_PER_ORDER)
    special_requests: Optional[str] = None

class Order(BaseModel):
    order_id: str
    items: List[OrderItem]
    special_requests: Optional[str] = None
    total_price: float
    status: str
    timestamp: str
    needs_human_review: bool = False
    confirmation_token: Optional[str] = None

class UpdateOrderStatusRequest(BaseModel):
    order_id: str
    status: str

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        raw = (v or "").strip().lower()
        # Tillåt direktvärden eller en känd alias-mappning. Okända värden ska INTE
        # tyst falla tillbaka på "pending" – det skulle dölja UI-buggar.
        accepted = {
            *order_integrity.ALLOWED_ORDER_STATUSES,
            "nya", "ny", "new",
            "redo", "ready_to_pickup", "done",
            "klar", "complete",
            "review", "behover_granskning", "behovsgranska",
            "cancel", "avbruten",
        }
        if raw not in accepted:
            raise ValueError(f"Otillåten status: {v}")
        return order_integrity.normalize_status(raw)

# ==================== FLOW REGISTRY (multi-tenant / unik logik) ====================
# Nya flöden: lägg till en handler-funktion och registrera här. Ingen if/else i webhook.
# Idag: bara "standard". Vid behov kan restaurants.flow_type eller restaurant_settings.flow_type styra vilken som anropas.
FLOW_HANDLERS = {"standard": None}  # None = nuvarande inline-logik; vid nytt flöde: def handle_xy(...): ... och FLOW_HANDLERS["xy"] = handle_xy


def get_flow_handler(flow_type: Optional[str] = None):
    """Returnerar handler för flow_type. Om okänd eller None används 'standard'."""
    key = (flow_type or "standard").strip().lower()
    return FLOW_HANDLERS.get(key, FLOW_HANDLERS["standard"])

# ==================== HELPER FUNCTIONS ====================

def _parse_items_from_params(params: dict, rest_id: Optional[str] = None) -> list:
    """Extrahera items från params. rest_id = vilken pizzeria (för meny-namn). Stödjer items, order.items, full_order.items, maträtter."""
    items = params.get("items", [])
    if not items and "order" in params:
        items = params.get("order", {}).get("items", [])
    if not items and "full_order" in params:
        items = params.get("full_order", {}).get("items", [])
    if not items and "maträtter" in params:
        items = params.get("maträtter", [])
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if isinstance(it, dict) and "item" in it and isinstance(it.get("item"), dict):
            d = dict(it["item"])
        elif isinstance(it, dict):
            d = dict(it)
        else:
            continue
        if "itemId" in d and "id" not in d:
            d["id"] = d.pop("itemId")
        if "qty" in d and "quantity" not in d:
            d["quantity"] = d.pop("qty")
        if "specialRequests" in d and "special_requests" not in d:
            d["special_requests"] = d.pop("specialRequests")
        if "name" not in d and d.get("id") is not None:
            mi = find_menu_item(int(d["id"]), rest_id)
            d["name"] = mi["name"] if mi else f"Artikel {d['id']}"
        out.append(d)
    return out

def load_menu(rest_id: Optional[str] = None) -> dict:
    """Load menu: rest_id=None eller Gislegrillen_01 → menu.json. Annars menu_{rest_id}.json, fallback menu.json. Ingen blandning mellan pizzerior."""
    empty = {"pizzas": [], "kebabs": [], "burgers": [], "sides": [], "drinks": []}
    if not rest_id or rest_id.strip() == "Gislegrillen_01":
        path = MENU_FILE
    else:
        path = BASE_DIR / ("menu_%s.json" % rest_id.strip())
        if not path.exists():
            path = MENU_FILE
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ ERROR: %s not found!" % path)
        return empty
    except Exception as e:
        print("❌ ERROR loading menu from %s: %s" % (path, e))
        return empty


# Fas 2 Diamond Polish: meny-cache TTL 3 min (per rest_id för framtida multi-tenant)
_MENU_CACHE: Dict[str, dict] = {}  # key -> {"data": menu_dict, "expires_at": float}
_MENU_CACHE_TTL_SEC = 180


def _menu_cache_key(rest_id: Optional[str]) -> str:
    return ("menu:%s" % rest_id) if rest_id else "menu"


def get_menu_cached(rest_id: Optional[str] = None) -> dict:
    """Return menu from cache if valid, else load from file and cache. rest_id för framtida per-tenant meny."""
    key = ("menu:%s" % rest_id) if rest_id else "menu"
    now = time.time()
    if key in _MENU_CACHE and now < _MENU_CACHE[key]["expires_at"]:
        return _MENU_CACHE[key]["data"]
    menu = load_menu(rest_id)
    _MENU_CACHE[key] = {"data": menu, "expires_at": now + _MENU_CACHE_TTL_SEC}
    return menu


def _invalidate_menu_cache(rest_id: Optional[str] = None) -> None:
    """Rensa meny-cache så nästa anrop laddar från fil/rest_id. Även menu_match-index."""
    if rest_id:
        k = _menu_cache_key(rest_id.strip())
        _MENU_CACHE.pop(k, None)
        menu_match.invalidate_menu_index_cache(rest_id.strip())
    else:
        _MENU_CACHE.clear()
        menu_match.invalidate_menu_index_cache(None)


def load_orders():
    """Load orders from JSON file"""
    try:
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_orders(orders):
    """Save orders to JSON file"""
    with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(orders, f, indent=2, ensure_ascii=False)

def find_menu_item(item_id: int, rest_id: Optional[str] = None):
    """Find menu item by ID across all categories. Uses cached menu (TTL 3 min)."""
    menu = get_menu_cached(rest_id)
    for category in menu.values():
        for item in category:
            if item.get('id') == item_id:
                return item
    return None


def _resolve_items_with_menu_match(
    items_data: list,
    rest_id: str,
) -> Tuple[bool, Optional[list], str]:
    """
    Meny-match v2.1: returnerar (True, resolved_rows, "") eller (False, None, json_result_str).
    json_result_str är redan serialiserad fel-payload (success:false + unmatchedItems).
    """
    menu = get_menu_cached(rest_id)
    if not menu_match.menu_has_items(menu):
        return (
            False,
            None,
            menu_match.place_order_fail_json(
                "Menyn kunde inte laddas för restaurangen",
                [],
            ),
        )
    index = menu_match.get_or_build_menu_index(rest_id, menu)
    if index is None:
        return (
            False,
            None,
            menu_match.place_order_fail_json(
                "Menyn kunde inte laddas för restaurangen",
                [],
            ),
        )
    ok, resolved, unmatched = menu_match.resolve_order_items(items_data, index, rest_id)
    if not ok:
        return (
            False,
            None,
            menu_match.place_order_fail_json(
                "En eller flera rätter kunde inte matchas",
                unmatched,
            ),
        )
    return (True, resolved, "")


def calculate_total_price(items: List[OrderItem], rest_id: Optional[str] = None) -> float:
    """Calculate total price from order items. rest_id = vilken pizzeria (rätt meny, rätt priser)."""
    total = 0.0
    for item in items:
        menu_item = find_menu_item(item.id, rest_id)
        if menu_item:
            total += menu_item["price"] * item.quantity
    return total

def generate_order_id() -> str:
    """Generate unique order ID (undviker kollision vid flera orders/samme sekund)"""
    import random
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"ORD-{ts}-{random.randint(100, 999)}"

def print_kitchen_ticket(order: Order):
    """Print a beautiful kitchen ticket to console"""
    print("\n" + "="*60)
    print("🔔 KÖKS-BONG! 🔔".center(60))
    print("="*60)
    print(f"ORDER ID: {order.order_id}")
    print(f"TID: {order.timestamp}")
    print("-"*60)
    print("ARTIKLAR:")
    for item in order.items:
        print(f"  [{item.quantity}x] {item.name} ({item.price} kr)")
    print("-"*60)
    if order.special_requests:
        print(f"⚠️  SPECIAL: {order.special_requests}")
        print("-"*60)
    print(f"TOTALT: {order.total_price} kr")
    print("="*60)
    print(f"STATUS: {order.status.upper()}")
    print("="*60 + "\n")

def _insert_order_to_supabase(
    order: Order,
    restaurant_id: str,
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
    raw_transcript: Optional[str] = None,
    restaurant_uuid: Optional[str] = None,
) -> Optional[str]:
    """Insert order to Supabase (orders-tabell för KDS/Lovable Dashboard). Returnerar DB-radens id vid lyckad insert.
    restaurant_uuid: om None används RESTAURANT_UUID (bakåtkompat).
    Om kolumnen special_instructions saknas i DB försöker vi fallback utan den (order sparas ändå)."""
    if not _supabase_client:
        print("⚠️  Supabase insert SKIPPED: _supabase_client is None (SUPABASE_URL/SUPABASE_KEY saknas eller init misslyckades vid start)")
        return None

    def _normalize_order_status_for_ui(value: Optional[str]) -> str:
        """Lovable/KDS UI expects: pending/ready/completed."""
        v = (value or "").strip().lower()
        if v in ("pending", "ready", "completed"):
            return v
        if v in ("nya", "ny", "new"):
            return "pending"
        if v in ("redo", "ready_to_pickup", "done"):
            return "ready"
        if v in ("klar", "completed", "complete"):
            return "completed"
        return "pending"

    def _build_row(include_special_instructions: bool, include_notes: bool, include_sms_tracking: bool):
        items_json = []
        for i in order.items:
            item = {"id": i.id, "name": i.name, "quantity": i.quantity, "price": i.price}
            if include_notes:
                notes = (getattr(i, "special_requests", None) or "").strip() or None
                if notes:
                    item["notes"] = notes
            items_json.append(item)
        row = {
            "restaurant_id": restaurant_id or "default",
            "customer_name": customer_name or "",
            "customer_phone": customer_phone or "",
            "items": items_json,
            "total_price": float(order.total_price),
            "status": _normalize_order_status_for_ui(getattr(order, "status", None)),
            "raw_transcript": raw_transcript or "",
        }
        if include_sms_tracking:
            row["order_id"] = order.order_id
            row["sms_status"] = "pending" if customer_phone else "missing_phone"
            row["sms_to"] = customer_phone or ""
        if include_special_instructions:
            row["special_instructions"] = (order.special_requests or "").strip() or ""
        uuid_val = restaurant_uuid or RESTAURANT_UUID
        if uuid_val:
            row["restaurant_uuid"] = uuid_val
        else:
            print(
                "⚠️  Supabase-rad saknar restaurant_uuid (sätt RESTAURANT_UUID i Railway eller "
                "rad i public.restaurants med external_id). Lovable kan filtrera bort ordern."
            )
        return row

    def _do_insert(row: dict):
        resp = _supabase_client.table("orders").insert(row).execute()
        err = getattr(resp, "error", None)
        if err:
            raise RuntimeError(str(err))
        data = getattr(resp, "data", None)
        if not data:
            # RLS eller fel kan ge 200 med tom data utan exception (beroende på klient)
            raise RuntimeError(
                "Supabase orders.insert returnerade inga rader. Kontrollera RLS policies (INSERT för service_role) "
                "och att SUPABASE_KEY är service_role om Lovable/KDS ska se ordrar."
            )
        inserted = data[0] if isinstance(data, list) and data else {}
        return str(inserted.get("id") or "") or None

    # Först med special_instructions och notes (full funktionalitet)
    try:
        row = _build_row(include_special_instructions=True, include_notes=True, include_sms_tracking=True)
        db_order_id = _do_insert(row)
        print(f"✅ Order {order.order_id} sparad till Supabase (restaurant_id={restaurant_id})")
        return db_order_id
    except Exception as e:
        err_str = str(e).lower()
        # Kolumn saknas eller liknande – försök utan optionala fält.
        is_column_error = (
            "special_instructions" in err_str
            or "notes" in err_str
            or "order_id" in err_str
            or "sms_status" in err_str
            or "sms_to" in err_str
            or "sms_last_error" in err_str
            or "sms_sent_at" in err_str
            or ("column" in err_str and ("does not exist" in err_str or "undefined_column" in err_str))
        )
        if is_column_error:
            print("⚠️  Supabase: optionala kolumner saknas – sparar order utan vissa metadata. Kör senaste Supabase-migrationen för full SMS-spårning.")
            try:
                row = _build_row(include_special_instructions=False, include_notes=False, include_sms_tracking=False)
                db_order_id = _do_insert(row)
                print(f"✅ Order {order.order_id} sparad till Supabase (fallback, restaurant_id={restaurant_id})")
                return db_order_id
            except Exception as e2:
                print(f"⚠️  Supabase insert failed (fallback): {e2}")
                return None
        print(f"⚠️  Supabase insert failed: {e}")
        return None


def _build_order_row_for_supabase(
    *,
    order: Order,
    restaurant_id: str,
    restaurant_uuid: Optional[str],
    customer_name: Optional[str],
    customer_phone: Optional[str],
    raw_transcript: Optional[str],
    vapi_call_id: Optional[str],
    vapi_tool_call_id: Optional[str],
    idempotency_key: Optional[str],
    payload_hash: Optional[str],
    needs_review: bool,
    confirmation_token: Optional[str],
) -> Dict[str, Any]:
    """Bygg full Supabase-rad inklusive Fas 1 tekniska fält. Schema-fallback hanteras i order_service."""

    items_json: List[Dict[str, Any]] = []
    for it in order.items:
        item: Dict[str, Any] = {
            "id": it.id,
            "name": it.name,
            "quantity": int(it.quantity),
            "price": float(it.price) if it.price is not None else None,
        }
        sr = (getattr(it, "special_requests", None) or "").strip()
        if sr:
            item["notes"] = sr
        items_json.append(item)

    row: Dict[str, Any] = {
        "restaurant_id": restaurant_id or "default",
        "customer_name": customer_name or "",
        "customer_phone": customer_phone or "",
        "items": items_json,
        "total_price": float(order.total_price),
        "status": order_integrity.normalize_status(order.status),
        "raw_transcript": raw_transcript or "",
        "order_id": order.order_id,
        "sms_status": "pending" if customer_phone else "missing_phone",
        "sms_to": customer_phone or "",
        "special_instructions": (order.special_requests or "").strip(),
        "vapi_call_id": vapi_call_id,
        "vapi_tool_call_id": vapi_tool_call_id,
        "idempotency_key": idempotency_key,
        "payload_hash": payload_hash,
        "validation_version": order_integrity.VALIDATION_VERSION,
        "needs_human_review": bool(needs_review),
        "confirmation_token": confirmation_token,
        "source": "vapi",
    }
    uuid_val = restaurant_uuid or RESTAURANT_UUID
    if uuid_val:
        row["restaurant_uuid"] = uuid_val
    return row


def _build_draft_for_items(
    *,
    items: List[OrderItem],
    raw_items: List[dict],
    restaurant_uuid: Optional[str],
    special_requests: Optional[str],
) -> Dict[str, Any]:
    """
    Bygg canonical draft (utan att committa). Används av /draft_order och
    av place_order när ingen draft_token skickats med.
    """
    canonical_items = order_integrity.make_canonical_items_from_resolved(
        [{
            "id": it.id,
            "name": it.name,
            "quantity": it.quantity,
            "price": it.price,
            "special_requests": it.special_requests,
        } for it in items]
    )
    canonical_payload = order_integrity.build_canonical_payload(
        restaurant_uuid=restaurant_uuid,
        canonical_items=canonical_items,
        order_special_requests=(special_requests or "").strip(),
    )
    payload_hash = order_integrity.build_payload_hash(canonical_payload)
    total_price = order_integrity.safe_total_price(canonical_items)
    needs_review, low_confidence_rows = order_integrity.confidence_summary_for_resolved(
        [{
            "id": r.get("id") or it.id,
            "name": r.get("name") or it.name,
            "matchType": r.get("matchType"),
            "matchScore": r.get("matchScore"),
        } for r, it in zip(raw_items, items)]
    )
    needs_review = (not needs_review)  # True om någon rad är låg konfidens

    items_summary = [
        {"id": ci.item_id, "name": ci.name, "quantity": ci.quantity}
        for ci in canonical_items
    ]
    token, token_payload = confirmation.issue_draft_token(
        restaurant_uuid=restaurant_uuid,
        payload_hash=payload_hash,
        items_summary=items_summary,
        total_price=total_price,
        needs_human_review=needs_review,
    )
    return {
        "canonical_items": [ci.to_dict() for ci in canonical_items],
        "canonical_payload": canonical_payload,
        "payload_hash": payload_hash,
        "total_price": total_price,
        "draft_token": token,
        "expires_at": token_payload.get("expires_at"),
        "needs_human_review": needs_review,
        "low_confidence_rows": low_confidence_rows,
        "readback": confirmation.format_canonical_readback(
            [ci.to_dict() for ci in canonical_items],
            total_price,
            (special_requests or "").strip(),
        ),
    }


def _commit_order_supabase_first(
    *,
    items: List[OrderItem],
    raw_items: List[dict],
    rest_id: str,
    restaurant_id: str,
    restaurant_uuid: Optional[str],
    customer_name: Optional[str],
    customer_phone: Optional[str],
    raw_transcript: Optional[str],
    special_requests: Optional[str],
    vapi_call_id: Optional[str],
    vapi_tool_call_id: Optional[str],
    correlation_id: Optional[str],
    draft_token: Optional[str] = None,
    require_draft_token: bool = False,
) -> Dict[str, Any]:
    """
    Centralt commit-flöde för en beställning. Returnerar dict:
      {
        "success": bool,
        "order_id": str | None,
        "db_order_id": str | None,
        "total_price": float | None,
        "needs_human_review": bool,
        "idempotent_replay": bool,
        "error_code": str | None,
        "error_message": str | None,
      }

    Hot path:
      1. Bygg canonical_items, payload och idempotency key.
      2. Slå upp idempotency-rad. Completed → returnera cached response.
      3. Reservera idempotency-rad.
      4. Bygg Order, spara till orders.json som backup (non-blocking).
      5. Insert till Supabase.
      6. Skriv order_events.
      7. Markera idempotency completed.

    Vid Supabase-fel: fail idempotency, registrera tenant-failure (kan trigga
    pause), returnera success:false. Inga falska ordersuccess.
    """

    # 1. Canonical view + hash + key.
    canonical_items = order_integrity.make_canonical_items_from_resolved(
        [{
            "id": it.id,
            "name": it.name,
            "quantity": it.quantity,
            "price": it.price,
            "special_requests": it.special_requests,
        } for it in items]
    )
    canonical_payload = order_integrity.build_canonical_payload(
        restaurant_uuid=restaurant_uuid,
        canonical_items=canonical_items,
        order_special_requests=(special_requests or "").strip(),
    )
    payload_hash = order_integrity.build_payload_hash(canonical_payload)
    idempotency_key = order_integrity.build_idempotency_key(
        restaurant_uuid=restaurant_uuid,
        vapi_call_id=vapi_call_id,
        vapi_tool_call_id=vapi_tool_call_id,
        payload_hash=payload_hash,
    )

    # 2a. Validera draft-token om den krävs eller skickats. Detta ser till att
    #     AI inte kan committa en order som inte överensstämmer med canonical
    #     readback som kunden bekräftat.
    if draft_token or require_draft_token:
        ok, token_payload, err_code = confirmation.verify_draft_token(
            draft_token or "",
            expected_restaurant_uuid=restaurant_uuid,
            expected_payload_hash=payload_hash,
        )
        if not ok:
            order_service.write_order_event(
                _supabase_client,
                event_type="draft_token_invalid",
                restaurant_uuid=restaurant_uuid,
                restaurant_id=restaurant_id,
                order_id=None,
                correlation_id=correlation_id,
                payload={"error_code": err_code or "unknown"},
            )
            return {
                "success": False,
                "order_id": None,
                "db_order_id": None,
                "total_price": None,
                "needs_human_review": False,
                "idempotent_replay": False,
                "error_code": "DRAFT_TOKEN_INVALID",
                "error_message": (
                    "Beställningen behöver bekräftas igen. Läs upp den för kunden och be om ja."
                    if err_code != "EXPIRED"
                    else "Bekräftelsen har gått ut. Be kunden bekräfta beställningen igen."
                ),
                "idempotency_key": idempotency_key,
                "draft_error_code": err_code,
            }

    # 2. Idempotency lookup.
    existing, lookup_err = order_service.lookup_existing_idempotency(_supabase_client, idempotency_key)
    if existing and (existing.get("status") == "completed"):
        cached_response = existing.get("response") or {}
        print(
            f"order_integrity: replay för key={idempotency_key} → returnerar cached order {cached_response.get('order_id')}"
        )
        order_service.write_order_event(
            _supabase_client,
            event_type="idempotent_replay",
            restaurant_uuid=restaurant_uuid,
            restaurant_id=restaurant_id,
            order_id=cached_response.get("order_id"),
            correlation_id=correlation_id,
            payload={"idempotency_key": idempotency_key},
        )
        return {
            "success": True,
            "order_id": cached_response.get("order_id"),
            "db_order_id": existing.get("db_order_id"),
            "total_price": cached_response.get("total_price"),
            "needs_human_review": bool(cached_response.get("needs_human_review")),
            "idempotent_replay": True,
            "error_code": None,
            "error_message": None,
            "idempotency_key": idempotency_key,
        }

    # Felaktig table = degraded mode (varning, men fortsätt).
    degraded_idempotency = lookup_err == "missing_table"
    if degraded_idempotency:
        print("order_integrity: idempotency_records saknas – kör degraded mode (kör supabase_phase1_order_integrity.sql).")

    # 3. Försök reservera nyckeln.
    reserved = False
    if _supabase_client and not degraded_idempotency:
        ok, reserve_err = order_service.reserve_idempotency(
            _supabase_client,
            idempotency_key=idempotency_key,
            restaurant_uuid=restaurant_uuid,
            restaurant_id=restaurant_id,
            vapi_call_id=vapi_call_id,
            vapi_tool_call_id=vapi_tool_call_id,
            payload_hash=payload_hash,
        )
        if ok:
            reserved = True
        elif reserve_err == "duplicate":
            # Race: någon annan request hann före. Hämta deras resultat.
            existing2, _ = order_service.lookup_existing_idempotency(_supabase_client, idempotency_key)
            if existing2 and existing2.get("status") == "completed":
                cached_response = existing2.get("response") or {}
                return {
                    "success": True,
                    "order_id": cached_response.get("order_id"),
                    "db_order_id": existing2.get("db_order_id"),
                    "total_price": cached_response.get("total_price"),
                    "needs_human_review": bool(cached_response.get("needs_human_review")),
                    "idempotent_replay": True,
                    "error_code": None,
                    "error_message": None,
                    "idempotency_key": idempotency_key,
                }
            # Fortfarande processing eller failed → returnera mjukt fel.
            return {
                "success": False,
                "order_id": None,
                "db_order_id": None,
                "total_price": None,
                "needs_human_review": False,
                "idempotent_replay": False,
                "error_code": "DUPLICATE_IN_FLIGHT",
                "error_message": "En identisk beställning behandlas redan. Försök igen om en stund.",
                "idempotency_key": idempotency_key,
            }
        elif reserve_err == "missing_table":
            degraded_idempotency = True
        else:
            # Okänt fel – varna men gå vidare. Ingen falsk ordersuccess sker eftersom Supabase-insert ändå krävs nedan.
            print(f"order_integrity: reserve_idempotency fail: {reserve_err}")

    # 4. Bygg Order och kör legacy-flödet (orders.json backup + kitchen ticket).
    needs_review, low_confidence = order_integrity.confidence_summary_for_resolved(
        [{
            "id": r.get("id") or it.id,
            "name": r.get("name") or it.name,
            "matchType": r.get("matchType"),
            "matchScore": r.get("matchScore"),
        } for r, it in zip(raw_items, items)]
    )
    needs_review = (not needs_review)  # True om någon rad är låg konfidens

    try:
        order = _process_place_order(items, special_requests, rest_id=rest_id)
    except HTTPException as he:
        if reserved:
            order_service.fail_idempotency(_supabase_client, idempotency_key, f"process_failure: {he.detail}")
        return {
            "success": False,
            "order_id": None,
            "db_order_id": None,
            "total_price": None,
            "needs_human_review": False,
            "idempotent_replay": False,
            "error_code": "ORDER_PROCESS_ERROR",
            "error_message": str(he.detail),
            "idempotency_key": idempotency_key,
        }

    if needs_review:
        order.needs_human_review = True
        order.status = "needs_review"
        # Skriv över i orders.json så lokal dashboard ser rätt status.
        try:
            orders = load_orders()
            for o in orders:
                if o.get("order_id") == order.order_id:
                    o["status"] = "needs_review"
                    o["needs_human_review"] = True
                    break
            save_orders(orders)
        except Exception:
            pass

    order_service.write_order_event(
        _supabase_client,
        event_type="order_built",
        restaurant_uuid=restaurant_uuid,
        restaurant_id=restaurant_id,
        order_id=order.order_id,
        correlation_id=correlation_id,
        payload={
            "items": [it.model_dump() for it in order.items],
            "total_price": float(order.total_price),
            "needs_human_review": needs_review,
            "low_confidence_rows": low_confidence,
            "idempotency_key": idempotency_key,
            "payload_hash": payload_hash,
        },
    )

    # 5. Insert i Supabase.
    db_order_id: Optional[str] = None
    db_error: Optional[str] = None
    if _supabase_client:
        row = _build_order_row_for_supabase(
            order=order,
            restaurant_id=restaurant_id,
            restaurant_uuid=restaurant_uuid,
            customer_name=customer_name,
            customer_phone=customer_phone,
            raw_transcript=raw_transcript,
            vapi_call_id=vapi_call_id,
            vapi_tool_call_id=vapi_tool_call_id,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            needs_review=needs_review,
            confirmation_token=None,
        )
        db_order_id, db_error = order_service.insert_order_row(_supabase_client, row)
        if db_error:
            print(f"order_integrity: Supabase insert FAIL idempotency_key={idempotency_key} err={db_error}")
            ops_agent.record_supabase_failure(
                _supabase_client,
                restaurant_uuid=restaurant_uuid,
                restaurant_id=restaurant_id,
                error_message=db_error,
                correlation_id=correlation_id,
                order_id=order.order_id,
            )
            order_service.write_order_event(
                _supabase_client,
                event_type="supabase_insert_failed",
                restaurant_uuid=restaurant_uuid,
                restaurant_id=restaurant_id,
                order_id=order.order_id,
                correlation_id=correlation_id,
                payload={"error": db_error[:500], "idempotency_key": idempotency_key},
            )
            if reserved:
                order_service.fail_idempotency(_supabase_client, idempotency_key, db_error)

            if ORDER_REQUIRE_DB_COMMIT:
                # Inga falska bekräftelser i produktion.
                return {
                    "success": False,
                    "order_id": None,
                    "db_order_id": None,
                    "total_price": None,
                    "needs_human_review": False,
                    "idempotent_replay": False,
                    "error_code": "SUPABASE_COMMIT_FAILED",
                    "error_message": "Beställningen kunde inte sparas just nu. Försök igen.",
                    "idempotency_key": idempotency_key,
                }
            # Annars (utvecklingsläge): låt JSON-version stå kvar och returnera success med varning.
        else:
            ops_agent.record_supabase_success(
                _supabase_client,
                restaurant_uuid=restaurant_uuid,
                restaurant_id=restaurant_id,
                order_id=order.order_id,
            )
            order_service.write_order_event(
                _supabase_client,
                event_type="order_committed",
                restaurant_uuid=restaurant_uuid,
                restaurant_id=restaurant_id,
                order_id=order.order_id,
                correlation_id=correlation_id,
                payload={"db_order_id": db_order_id, "idempotency_key": idempotency_key},
            )
    else:
        # Ingen Supabase-klient: utveckling/lokalt. ORDER_REQUIRE_DB_COMMIT styr om vi ska
        # neka eller acceptera. Default i prod: kräv DB.
        if ORDER_REQUIRE_DB_COMMIT:
            return {
                "success": False,
                "order_id": None,
                "db_order_id": None,
                "total_price": None,
                "needs_human_review": False,
                "idempotent_replay": False,
                "error_code": "SUPABASE_NOT_CONFIGURED",
                "error_message": "Beställning kan inte tas emot just nu. Försök igen.",
                "idempotency_key": idempotency_key,
            }

    # 6. Markera idempotency-rad completed.
    response_payload = {
        "order_id": order.order_id,
        "total_price": float(order.total_price),
        "needs_human_review": needs_review,
    }
    if reserved:
        order_service.complete_idempotency(
            _supabase_client,
            idempotency_key=idempotency_key,
            order_id=order.order_id,
            db_order_id=db_order_id,
            response_payload=response_payload,
        )

    return {
        "success": True,
        "order_id": order.order_id,
        "db_order_id": db_order_id,
        "total_price": float(order.total_price),
        "needs_human_review": needs_review,
        "idempotent_replay": False,
        "error_code": None,
        "error_message": None,
        "idempotency_key": idempotency_key,
    }


def _format_order_sms(order: Order) -> str:
    """Formatera beställning till SMS-text enligt spec."""
    lines = ["Hej! Detta är din orderbekräftelse från Gislegrillen.", ""]
    for item in order.items:
        part = f"{item.quantity}x {item.name}"
        if item.special_requests and item.special_requests.strip():
            part += f" {item.special_requests.strip()}"
        lines.append(part)
    lines.extend(["", "Är din beställning felaktig? Ring oss: +46760445700"])
    return "\n".join(lines)


def _normalize_phone_for_sms(value: Any) -> Optional[str]:
    """Normalisera kundnummer till E.164-liknande format. Returnerar None för osäkra värden."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = re.sub(r"^(tel:|sms:)", "", raw, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"[^\d+]", "", raw)
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) < 7 or len(digits) > 15:
        return None
    if cleaned.startswith("+"):
        return "+" + digits
    if digits.startswith("0") and len(digits) > 1:
        return "+46" + digits[1:]
    if digits.startswith("46"):
        return "+" + digits
    return "+" + digits


def _blocked_sms_recipient_numbers() -> set:
    blocked = {VONAGE_FROM_NUMBER, RESTAURANT_CONTACT_NUMBER}
    if SMS_EXCLUDED_NUMBERS:
        blocked.update(part.strip() for part in SMS_EXCLUDED_NUMBERS.split(","))
    return {n for raw in blocked if (n := _normalize_phone_for_sms(raw))}


def _is_blocked_sms_recipient(phone: Optional[str]) -> bool:
    normalized = _normalize_phone_for_sms(phone)
    return bool(normalized and normalized in _blocked_sms_recipient_numbers())


def _first_phone_from_paths(source: dict, paths: List[Tuple[str, ...]]) -> Optional[str]:
    for path in paths:
        cur: Any = source
        for key in path:
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(key)
        phone = _normalize_phone_for_sms(cur)
        if phone:
            return phone
    return None


def _recursive_customer_phone_search(value: Any, path: Tuple[str, ...] = ()) -> Optional[str]:
    """Sök försiktigt efter kund-/caller-nummer utan att råka ta restaurangens destination/to-nummer."""
    if isinstance(value, dict):
        for key, child in value.items():
            key_norm = re.sub(r"[^a-z0-9]", "", str(key).lower())
            path_norm = tuple(re.sub(r"[^a-z0-9]", "", str(p).lower()) for p in path)
            in_customer_context = any(p in {"customer", "caller", "from"} for p in path_norm)
            safe_key = (
                key_norm in {"from", "caller", "callerid", "callernumber", "callerphone"}
                or ("customer" in key_norm and ("number" in key_norm or "phone" in key_norm))
                or (in_customer_context and key_norm in {"number", "phone", "phonenumber", "mobile"})
            )
            blocked_key = (
                key_norm in {"to", "destination", "phonenumberid", "id"}
                or "assistant" in key_norm
                or "restaurant" in key_norm
                or "business" in key_norm
                or "twilio" in key_norm
                or "vonage" in key_norm
            )
            if safe_key and not blocked_key:
                phone = _normalize_phone_for_sms(child)
                if phone:
                    return phone
            if not blocked_key and isinstance(child, (dict, list)):
                phone = _recursive_customer_phone_search(child, path + (str(key),))
                if phone:
                    return phone
    elif isinstance(value, list):
        for child in value:
            phone = _recursive_customer_phone_search(child, path)
            if phone:
                return phone
    return None


def send_sms_order_confirmation(order: Order, to_number: str) -> bool:
    """
    Skicka SMS-orderbekräftelse via Vonage.
    Returnerar True vid lyckat skickande, False annars.
    Blockerar ALDRIG – fel loggas men kastas inte.
    """
    return _send_sms_order_confirmation_result(order, to_number)["ok"]


def _send_sms_order_confirmation_result(order: Order, to_number: str) -> dict:
    """Skicka SMS och returnera strukturerad status för Supabase-spårning."""
    to = _normalize_phone_for_sms(to_number)
    if not to:
        print("⚠️  No valid customer phone number. Skipping SMS.")
        return {"ok": False, "to": "", "error": "missing_or_invalid_customer_phone"}
    if _is_blocked_sms_recipient(to):
        print("⚠️  SMS recipient is a restaurant/provider number, not a customer. Skipping SMS.")
        return {"ok": False, "to": to, "error": "blocked_business_or_provider_number"}
    if not VONAGE_API_KEY or not VONAGE_API_SECRET or not VONAGE_FROM_NUMBER:
        print("⚠️  Vonage not configured. Skipping SMS.")
        return {"ok": False, "to": to, "error": "vonage_not_configured"}
    print(f"DEBUG SMS: Vonage config OK, calling API for to_number={to_number}")
    text = _format_order_sms(order)
    try:
        r = requests.post(
            "https://rest.nexmo.com/sms/json",
            # requests encodes this as application/x-www-form-urlencoded, including
            # special characters in credentials/text required by Vonage's stricter parser.
            data={
                "api_key": VONAGE_API_KEY,
                "api_secret": VONAGE_API_SECRET,
                "from": VONAGE_FROM_NUMBER,
                "to": to,
                "text": text,
            },
            timeout=10,
        )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        msgs = data.get("messages") or []
        print(f"DEBUG SMS: Vonage API response status={r.status_code}, data={json.dumps(data, ensure_ascii=False)[:300]}")
        if msgs and msgs[0].get("status") == "0":
            print(f"✅ SMS orderbekräftelse skickad till {to} (order {order.order_id})")
            return {"ok": True, "to": to, "error": "", "provider_status": "0"}
        err = (msgs[0].get("error-text") if msgs else None) or r.text
        print(f"⚠️  Vonage SMS FAILED: {err}")
        if "Bad Credentials" in str(err):
            print("   → Kolla VONAGE_API_KEY och VONAGE_API_SECRET i Railway Variables. Kopiera exakt från Vonage Dashboard.")
        elif "invalid" in str(err).lower() or "from" in str(err).lower():
            print("   → VONAGE_FROM_NUMBER måste vara ett nummer du äger i Vonage (t.ex. virtuellt nummer). Format: +46701234567")
        provider_status = msgs[0].get("status") if msgs else str(r.status_code)
        return {"ok": False, "to": to, "error": str(err), "provider_status": provider_status}
    except Exception as e:
        print(f"⚠️  Vonage SMS error: {e}")
        return {"ok": False, "to": to, "error": str(e)}

def _get_customer_phone_from_webhook(body: dict, params: Optional[dict] = None) -> Optional[str]:
    """Hämta kundens telefonnummer från Vapi webhook-payload.
    Avsiktligt exkluderas generiska destination/to/phoneNumber-fält som ofta är restaurangens Vapi-nummer."""
    if not isinstance(body, dict):
        body = {}
    if params is not None and not isinstance(params, dict):
        params = {}
    param_paths = (
        ("customer_phone",),
        ("customerPhone",),
        ("customer_number",),
        ("customerNumber",),
        ("phone",),
        ("phone_number",),
        ("phoneNumber",),
    )
    body_paths = (
        ("message", "call", "customer", "number"),
        ("message", "call", "customer", "phone"),
        ("message", "call", "customer", "phoneNumber"),
        ("call", "customer", "number"),
        ("call", "customer", "phone"),
        ("call", "customer", "phoneNumber"),
        ("message", "customer", "number"),
        ("message", "customer", "phone"),
        ("customer", "number"),
        ("customer", "phone"),
        ("message", "call", "customerNumber"),
        ("message", "call", "callerNumber"),
        ("message", "call", "from"),
        ("call", "customerNumber"),
        ("call", "callerNumber"),
        ("call", "from"),
        ("message", "customerNumber"),
        ("message", "callerNumber"),
        ("message", "from"),
        ("customerNumber",),
        ("callerNumber",),
        ("from",),
    )
    phone = None
    for source, paths_to_try in ((params or {}, param_paths), (body, body_paths)):
        phone = _first_phone_from_paths(source, list(paths_to_try))
        if phone:
            if _is_blocked_sms_recipient(phone):
                print("DEBUG SMS: candidate phone is restaurant/provider number, ignoring")
                phone = None
                continue
            break
        phone = _recursive_customer_phone_search(source)
        if phone:
            if _is_blocked_sms_recipient(phone):
                print("DEBUG SMS: recursive candidate phone is restaurant/provider number, ignoring")
                phone = None
                continue
            break
    print(f"DEBUG SMS: phone sökväg -> found={'YES' if phone else 'NO'}")
    return phone


def _cache_customer_phone_for_call(call_id: str, phone: str) -> None:
    if not call_id or not phone:
        return
    _CALL_CUSTOMER_PHONE_CACHE[str(call_id)] = {"phone": phone, "ts": time.time()}
    if len(_CALL_CUSTOMER_PHONE_CACHE) > _CALL_CACHE_MAX_SIZE:
        now = time.time()
        expired = [k for k, v in _CALL_CUSTOMER_PHONE_CACHE.items() if (now - v["ts"]) > _CALL_CACHE_TTL_SEC]
        for k in expired:
            del _CALL_CUSTOMER_PHONE_CACHE[k]


def _get_cached_customer_phone_for_call(call_id: str) -> Optional[str]:
    if not call_id:
        return None
    entry = _CALL_CUSTOMER_PHONE_CACHE.get(str(call_id))
    if not entry:
        return None
    if (time.time() - entry["ts"]) > _CALL_CACHE_TTL_SEC:
        del _CALL_CUSTOMER_PHONE_CACHE[str(call_id)]
        return None
    return entry.get("phone")


def _fetch_vapi_call_record(call_id: str) -> Optional[dict]:
    """Hämta call-objekt från Vapi API (fallback när webhook saknar kundnummer)."""
    if not call_id or not VAPI_API_KEY:
        return None
    try:
        r = requests.get(
            f"https://api.vapi.ai/call/{call_id}",
            headers={"Authorization": f"Bearer {VAPI_API_KEY}"},
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, dict) else None
        print(f"DEBUG SMS: Vapi GET /call/{call_id} status={r.status_code}")
    except Exception as e:
        print(f"DEBUG SMS: Vapi GET /call failed: {e}")
    return None


def _customer_phone_from_vapi_call_record(record: dict) -> Optional[str]:
    """Extrahera kundnummer från Vapi call-record (customer.number, message.customer, etc.)."""
    if not isinstance(record, dict):
        return None
    paths = (
        ("customer", "number"),
        ("customer", "phone"),
        ("customer", "phoneNumber"),
    )
    phone = _first_phone_from_paths(record, list(paths))
    if phone:
        return phone
    return _recursive_customer_phone_search(record)


def _resolve_customer_phone(body: dict, params: Optional[dict] = None) -> Optional[str]:
    """
    Hämta kundens mobil för SMS-bekräftelse.
    Ordning: explicit params/body → cache per call_id → Vapi API GET /call/{id}.
    """
    phone = _get_customer_phone_from_webhook(body, params)
    if phone:
        call_id = _get_call_id_from_webhook(body)
        if call_id:
            _cache_customer_phone_for_call(call_id, phone)
        return phone

    call_id = _get_call_id_from_webhook(body)
    if not call_id:
        return None

    cached = _get_cached_customer_phone_for_call(call_id)
    if cached:
        print(f"DEBUG SMS: using cached phone for call_id={call_id}")
        return cached

    record = _fetch_vapi_call_record(call_id)
    if not record:
        return None

    api_phone = _customer_phone_from_vapi_call_record(record)
    if not api_phone:
        print(f"DEBUG SMS: Vapi API call {call_id} has no extractable customer phone")
        return None
    if _is_blocked_sms_recipient(api_phone):
        print(
            f"DEBUG SMS: Vapi API customer.number={api_phone} is restaurant/provider – "
            "SMS kräver customer_phone från samtalet eller Vonage caller-ID-fix"
        )
        return None

    _cache_customer_phone_for_call(call_id, api_phone)
    print(f"DEBUG SMS: resolved phone from Vapi API for call_id={call_id}")
    return api_phone


def _get_restaurant_id_from_webhook(body: dict) -> str:
    """Legacy: returnerar bara restaurant_id. Använd _get_restaurant_from_webhook för multi-tenant."""
    rid, _ = _get_restaurant_from_webhook(body, None)
    return rid


# Cache: call_id -> (restaurant_id, restaurant_uuid) så att place_order vet vilken restaurang även om anropet saknar query-params.
# TTL 1 timme; rensa vid skriv om cache blir för stor. Dict/Tuple för Python 3.7/3.8-kompatibilitet.
_CALL_RESTAURANT_CACHE: Dict[str, dict] = {}
_CALL_CACHE_TTL_SEC = 3600
_CALL_CACHE_MAX_SIZE = 2000

# Cache: call_id -> kundens normaliserade mobil (för SMS) när vi hittat den i webhook eller Vapi API.
_CALL_CUSTOMER_PHONE_CACHE: Dict[str, dict] = {}

# ==================== FAS 1: SAFETY NET ====================
# Aktiva-tenant-set: uppdateras var 1:e minut från DB. Vid cache-användning validerar vi mot denna.
_ACTIVE_TENANT_UUIDS: set = set()
_ACTIVE_TENANT_LAST_REFRESH: float = 0
_ACTIVE_TENANT_REFRESH_INTERVAL_SEC = 60

# Config-cache: rest_id -> {restaurant_id, restaurant_uuid, ts, throttle_bucket_size, throttle_refill_per_sec, tenant_secrets?}. TTL 5 min.
_CONFIG_CACHE: Dict[str, dict] = {}
_CONFIG_CACHE_TTL_SEC = 300

# Circuit breaker: rest_id -> {fail_count, first_fail_ts, open_until_ts, alert_sent}
_CIRCUIT_BREAKER: Dict[str, dict] = {}
_CIRCUIT_FAIL_THRESHOLD = 5
_CIRCUIT_WINDOW_SEC = 60
_CIRCUIT_OPEN_DURATION_SEC = 60

# Token bucket: rest_id -> {tokens, last_ts}. Default 20 bucket, 0.1 refill/s.
_TOKEN_BUCKET: Dict[str, dict] = {}
_TOKEN_BUCKET_DEFAULT_SIZE = 20
_TOKEN_BUCKET_DEFAULT_REFILL_PER_SEC = 0.1


def _get_call_id_from_webhook(body: dict) -> Optional[str]:
    """Hämta Vapi call id från body (message.call.id). Returnerar alltid str eller None (säker som dict-nyckel)."""
    if not isinstance(body, dict):
        return None
    msg = body.get("message")
    if not isinstance(msg, dict):
        return None
    call = msg.get("call")
    if not isinstance(call, dict):
        return None
    raw = call.get("id") or call.get("callId")
    if raw is None:
        return None
    return str(raw).strip() or None


def _get_raw_transcript_from_webhook(body: dict) -> str:
    """Hämta rå transkript från Vapi webhook-body om det finns. Returnerar tom sträng om inte."""
    if not isinstance(body, dict):
        return ""
    msg = body.get("message") or {}
    call = (msg.get("call") if isinstance(msg, dict) else None) or body.get("call") or {}
    # Vanliga ställen Vapi kan skicka transkript
    for val in (
        msg.get("transcript") if isinstance(msg, dict) else None,
        msg.get("content") if isinstance(msg, dict) else None,
        call.get("transcript") if isinstance(call, dict) else None,
        body.get("transcript"),
    ):
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, list):
            # content kan vara lista med {type, content/text}
            parts = []
            for item in val:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                elif isinstance(item, str) and item.strip():
                    parts.append(item.strip())
            if parts:
                return "\n".join(parts)
    return ""


def _cache_restaurant_for_call(call_id: str, restaurant_id: str, restaurant_uuid: Optional[str]) -> None:
    """Spara call_id -> restaurang i tillfällig cache. Rensar utgångna om cache är för stor."""
    if not call_id:
        return
    now = time.time()
    _CALL_RESTAURANT_CACHE[str(call_id)] = {
        "restaurant_id": restaurant_id,
        "restaurant_uuid": restaurant_uuid,
        "ts": now,
    }
    if len(_CALL_RESTAURANT_CACHE) <= _CALL_CACHE_MAX_SIZE:
        return
    # Rensa utgångna
    expired = [k for k, v in _CALL_RESTAURANT_CACHE.items() if (now - v["ts"]) > _CALL_CACHE_TTL_SEC]
    for k in expired:
        del _CALL_RESTAURANT_CACHE[k]
    # Om fortfarande för stor, ta bort äldsta
    while len(_CALL_RESTAURANT_CACHE) > _CALL_CACHE_MAX_SIZE:
        oldest = min(_CALL_RESTAURANT_CACHE.items(), key=lambda x: x[1]["ts"])
        del _CALL_RESTAURANT_CACHE[oldest[0]]


def _get_restaurant_for_webhook(body: dict, request: Optional[Request] = None) -> Tuple[str, Optional[str]]:
    """Hämta (restaurant_id, restaurant_uuid) för detta anrop. Använder cache på call_id om tillgänglig, annars lookup från rest_id."""
    call_id = _get_call_id_from_webhook(body)
    if call_id and call_id in _CALL_RESTAURANT_CACHE:
        entry = _CALL_RESTAURANT_CACHE[call_id]
        if (time.time() - entry["ts"]) <= _CALL_CACHE_TTL_SEC:
            return (entry["restaurant_id"], entry["restaurant_uuid"])
    restaurant_id, restaurant_uuid = _get_restaurant_from_webhook(body, request)
    if call_id:
        _cache_restaurant_for_call(call_id, restaurant_id, restaurant_uuid)
    return (restaurant_id, restaurant_uuid)


def _decrypt_tenant_config(encrypted_b64: str) -> Optional[Dict[str, Any]]:
    """Fas 2: Dekryptera encrypted_config från restaurant_secrets. Returnerar dict eller None."""
    if not _fernet or not encrypted_b64:
        return None
    try:
        raw = _fernet.decrypt(encrypted_b64.encode() if isinstance(encrypted_b64, str) else encrypted_b64)
        return json.loads(raw.decode())
    except Exception as e:
        print("⚠️  Decrypt tenant config failed: %s" % e)
        return None


def _encrypt_tenant_config(plain_dict: Dict[str, Any]) -> Optional[str]:
    """Fas 2: Kryptera config-dict till base64-sträng för lagring i restaurant_secrets."""
    if not _fernet:
        return None
    try:
        raw = json.dumps(plain_dict).encode()
        return _fernet.encrypt(raw).decode()
    except Exception as e:
        print("⚠️  Encrypt tenant config failed: %s" % e)
        return None


def _get_restaurant_from_webhook(body: dict, request: Optional[Request] = None) -> Tuple[str, Optional[str]]:
    """Multi-tenant: hämta rest_id från query (rest_id) eller body, slå upp i Supabase restaurants.
    Returnerar (restaurant_id, restaurant_uuid). Om lookup misslyckas: (rest_id, RESTAURANT_UUID)."""
    rest_id = None
    if request:
        rest_id = request.query_params.get("rest_id")
    if not rest_id and isinstance(body, dict):
        rest_id = body.get("rest_id")
        if not rest_id:
            msg = body.get("message")
            if isinstance(msg, dict):
                call = msg.get("call")
                if isinstance(call, dict):
                    meta = call.get("metadata")
                    if isinstance(meta, dict):
                        rest_id = meta.get("rest_id")
    rest_id = (rest_id or "Gislegrillen_01").strip()
    if _supabase_client:
        try:
            r = _supabase_client.table("restaurants").select("id, external_id").eq("external_id", rest_id).is_("deleted_at", "null").limit(1).execute()
            if r.data and len(r.data) > 0:
                row = r.data[0]
                return (row["external_id"], str(row["id"]))
        except Exception:
            try:
                r = _supabase_client.table("restaurants").select("id, external_id").eq("external_id", rest_id).limit(1).execute()
                if r.data and len(r.data) > 0:
                    row = r.data[0]
                    return (row["external_id"], str(row["id"]))
            except Exception as e:
                print(f"⚠️  Restaurant lookup failed for rest_id={rest_id}: {e}")
    return (rest_id, RESTAURANT_UUID)


def _refresh_active_tenant_set() -> None:
    """Uppdatera _ACTIVE_TENANT_UUIDS från DB. Anropas lazy vid behov.
    Fas 3: endast restauranger med deleted_at IS NULL räknas som aktiva."""
    global _ACTIVE_TENANT_LAST_REFRESH, _ACTIVE_TENANT_UUIDS
    now = time.time()
    if now - _ACTIVE_TENANT_LAST_REFRESH < _ACTIVE_TENANT_REFRESH_INTERVAL_SEC:
        return
    _ACTIVE_TENANT_LAST_REFRESH = now
    if not _supabase_client:
        return
    try:
        r = _supabase_client.table("restaurants").select("id").is_("deleted_at", "null").execute()
        if r.data:
            _ACTIVE_TENANT_UUIDS = {str(row["id"]) for row in r.data}
        else:
            _ACTIVE_TENANT_UUIDS = set()
    except Exception as e:
        try:
            r = _supabase_client.table("restaurants").select("id").execute()
            if r.data:
                _ACTIVE_TENANT_UUIDS = {str(row["id"]) for row in r.data}
            else:
                _ACTIVE_TENANT_UUIDS = set()
            print("⚠️  Fas 3: kör supabase_fas3_deleted_at.sql för soft delete (deleted_at saknas)")
        except Exception as e2:
            print(f"⚠️  Active tenant refresh failed: {e2}")


def _is_tenant_active(restaurant_uuid: Optional[str]) -> bool:
    """Returnera True om restaurant_uuid finns i aktiva-tenant-set. Uppdaterar set om det är för gammalt.
    Saknas UUID (legacy) eller är aktiv-listan tom efter refresh (t.ex. RLS döljer restaurants) → tillåt
    ändå så att ordrar/SMS/Supabase inte blockeras av en tom cache."""
    if not restaurant_uuid:
        return True
    _refresh_active_tenant_set()
    if not _ACTIVE_TENANT_UUIDS:
        print(
            "⚠️  _ACTIVE_TENANT_UUIDS är tom (kolla RLS på restaurants eller DB). "
            "Tillåter ändå webhook för rest_uuid=%s…" % (str(restaurant_uuid)[:8],)
        )
        return True
    return str(restaurant_uuid) in _ACTIVE_TENANT_UUIDS


def _get_rest_id_from_request(request: Optional[Request], body: dict) -> str:
    """Hämta rest_id från query eller body (för circuit breaker och token bucket innan lookup)."""
    if request:
        r = request.query_params.get("rest_id")
        if r:
            return r.strip()
    if isinstance(body, dict):
        r = body.get("rest_id")
        if r:
            return str(r).strip()
        msg = body.get("message")
        if isinstance(msg, dict):
            call = msg.get("call")
            if isinstance(call, dict):
                meta = call.get("metadata")
                if isinstance(meta, dict):
                    r = meta.get("rest_id")
                    if r:
                        return str(r).strip()
    return "Gislegrillen_01"


def _fetch_restaurant_config_from_db(rest_id: str) -> Optional[dict]:
    """Fas 2: Hämta full config från DB (restaurants + restaurant_secrets). Returnerar dict eller None.
    Tolerant om throttle-kolumner eller restaurant_secrets saknas (fallback till default)."""
    if not _supabase_client:
        return None
    try:
        r = _supabase_client.table("restaurants").select(
            "id, external_id, throttle_bucket_size, throttle_refill_per_sec"
        ).eq("external_id", rest_id).is_("deleted_at", "null").limit(1).execute()
    except Exception:
        try:
            r = _supabase_client.table("restaurants").select(
                "id, external_id, throttle_bucket_size, throttle_refill_per_sec"
            ).eq("external_id", rest_id).is_("deleted_at", "null").limit(1).execute()
        except Exception:
            try:
                r = _supabase_client.table("restaurants").select("id, external_id").eq("external_id", rest_id).is_("deleted_at", "null").limit(1).execute()
            except Exception as e:
                print("⚠️  fetch_restaurant_config_from_db failed: %s" % e)
                return None
    if not r.data or len(r.data) == 0:
        return None
    row = r.data[0]
    restaurant_uuid = str(row["id"])
    bucket = _TOKEN_BUCKET_DEFAULT_SIZE
    refill = _TOKEN_BUCKET_DEFAULT_REFILL_PER_SEC
    if row.get("throttle_bucket_size") is not None:
        try:
            bucket = int(row["throttle_bucket_size"])
        except (TypeError, ValueError):
            pass
    if row.get("throttle_refill_per_sec") is not None:
        try:
            refill = float(row["throttle_refill_per_sec"])
        except (TypeError, ValueError):
            pass
    config = {
        "restaurant_id": row.get("external_id") or rest_id,
        "restaurant_uuid": restaurant_uuid,
        "throttle_bucket_size": bucket,
        "throttle_refill_per_sec": refill,
    }
    try:
        sec = _supabase_client.table("restaurant_secrets").select("encrypted_config").eq("restaurant_uuid", row["id"]).limit(1).execute()
        if sec.data and len(sec.data) > 0 and sec.data[0].get("encrypted_config"):
            dec = _decrypt_tenant_config(sec.data[0]["encrypted_config"])
            if dec:
                config["tenant_secrets"] = dec
    except Exception:
        pass
    return config


def _resolve_restaurant_by_external_id(rest_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Slå upp (restaurant_id, restaurant_uuid) baserat på external_id i Supabase.
    Använder samma config-cache som webhook-flödet om möjligt.
    Returnerar (None, None) om ej funnen eller Supabase ej konfigurerad.
    """
    if not rest_id:
        return (None, None)
    rid = rest_id.strip()
    now = time.time()
    if rid in _CONFIG_CACHE:
        entry = _CONFIG_CACHE[rid]
        if now - entry["ts"] <= _CONFIG_CACHE_TTL_SEC:
            return (entry.get("restaurant_id"), entry.get("restaurant_uuid"))
    if not _supabase_client:
        return (rid, None)
    try:
        resp = _supabase_client.table("restaurants").select("external_id, id").eq("external_id", rid).limit(1).execute()
        rows = getattr(resp, "data", None) or []
        if rows:
            ext = rows[0].get("external_id") or rid
            uuid_val = rows[0].get("id")
            return (ext, str(uuid_val) if uuid_val else None)
    except Exception as e:
        print(f"⚠️  _resolve_restaurant_by_external_id fail: {e}")
    return (rid, None)


def _get_restaurant_config_cached(body: dict, request: Optional[Request]) -> Tuple[Optional[str], Optional[str]]:
    """Fas 1+2: Hämta (restaurant_id, restaurant_uuid) med config-cache (5 min), throttle från DB, aktiva-tenant-validering.
    Returnerar (None, None) om tenant inte är aktiv (t.ex. nyss raderad)."""
    rest_id = _get_rest_id_from_request(request, body)
    now = time.time()
    # Config-cache träff
    if rest_id in _CONFIG_CACHE:
        entry = _CONFIG_CACHE[rest_id]
        if now - entry["ts"] <= _CONFIG_CACHE_TTL_SEC:
            if _is_tenant_active(entry.get("restaurant_uuid")):
                return (entry["restaurant_id"], entry["restaurant_uuid"])
            del _CONFIG_CACHE[rest_id]
    # Cache-miss: grundlookup + Fas 2 full config
    restaurant_id, restaurant_uuid = _get_restaurant_from_webhook(body, request)
    entry = {"restaurant_id": restaurant_id, "restaurant_uuid": restaurant_uuid, "ts": now,
             "throttle_bucket_size": _TOKEN_BUCKET_DEFAULT_SIZE, "throttle_refill_per_sec": _TOKEN_BUCKET_DEFAULT_REFILL_PER_SEC}
    db_config = _fetch_restaurant_config_from_db(rest_id)
    if db_config:
        entry["throttle_bucket_size"] = db_config.get("throttle_bucket_size", _TOKEN_BUCKET_DEFAULT_SIZE)
        entry["throttle_refill_per_sec"] = db_config.get("throttle_refill_per_sec", _TOKEN_BUCKET_DEFAULT_REFILL_PER_SEC)
        if db_config.get("tenant_secrets"):
            entry["tenant_secrets"] = db_config["tenant_secrets"]
    _CONFIG_CACHE[rest_id] = entry
    if not _is_tenant_active(restaurant_uuid):
        return (None, None)
    return (restaurant_id, restaurant_uuid)


def _circuit_breaker_allow(rest_id: str) -> bool:
    """Returnera True om anrop för denna rest_id ska tillåtas. Uppdaterar state vid fel (anropas separat)."""
    now = time.time()
    if rest_id not in _CIRCUIT_BREAKER:
        return True
    entry = _CIRCUIT_BREAKER[rest_id]
    if now < entry.get("open_until_ts", 0):
        return False
    # Circuit har stängt (tiden gått): återställ alert_sent så nästa öppning skickar notis igen
    entry["alert_sent"] = False
    return True


def _circuit_breaker_record_failure(rest_id: str) -> bool:
    """Registrera ett fel för rest_id. Returnerar True om breakern just öppnades (skicka alert)."""
    now = time.time()
    if rest_id not in _CIRCUIT_BREAKER:
        _CIRCUIT_BREAKER[rest_id] = {"fail_count": 0, "first_fail_ts": now, "open_until_ts": 0, "alert_sent": False}
    entry = _CIRCUIT_BREAKER[rest_id]
    entry["fail_count"] = entry.get("fail_count", 0) + 1
    if entry.get("first_fail_ts", now) < now - _CIRCUIT_WINDOW_SEC:
        entry["first_fail_ts"] = now
        entry["fail_count"] = 1
    if entry["fail_count"] >= _CIRCUIT_FAIL_THRESHOLD:
        entry["open_until_ts"] = now + _CIRCUIT_OPEN_DURATION_SEC
        if not entry.get("alert_sent"):
            entry["alert_sent"] = True
            return True
    return False


def _circuit_breaker_record_success(rest_id: str) -> None:
    """Vid lyckat anrop: nollställ räknare."""
    if rest_id in _CIRCUIT_BREAKER:
        _CIRCUIT_BREAKER[rest_id]["fail_count"] = 0
        _CIRCUIT_BREAKER[rest_id]["alert_sent"] = False


def _send_circuit_breaker_alert(rest_id: str) -> None:
    """Logga när circuit breaker öppnas (kolla Railway-/serverloggar)."""
    print(
        "⚠️  [ALERT] Circuit breaker ÖPPNAD för rest_id=%s – %d fel på %d s. Kontrollera konfiguration."
        % (rest_id, _CIRCUIT_FAIL_THRESHOLD, _CIRCUIT_WINDOW_SEC)
    )


# Diamond Polish Fas 1: SMS i bakgrunden + alert vid fel (rate-limit per rest_id)
_SMS_ALERT_LAST_SENT: Dict[str, float] = {}
_SMS_ALERT_RATE_LIMIT_SEC = 300


def _send_sms_failure_alert(rest_id: str, order_id: str, error_msg: str) -> None:
    """Logga SMS-fel (rate-limit: max 1 full logg per rest_id per 5 min)."""
    now = time.time()
    if rest_id in _SMS_ALERT_LAST_SENT and (now - _SMS_ALERT_LAST_SENT[rest_id]) < _SMS_ALERT_RATE_LIMIT_SEC:
        print("⚠️  SMS misslyckades igen för rest_id=%s (order %s), undertryckt (rate limit)" % (rest_id, order_id))
        return
    _SMS_ALERT_LAST_SENT[rest_id] = now
    print(
        "⚠️  [ALERT] SMS misslyckades – order_id %s, rest_id %s, fel: %s"
        % (order_id, rest_id, (error_msg or "okänt")[:200])
    )


def _update_order_sms_status(
    db_order_id: Optional[str],
    order_id: Optional[str],
    status: str,
    sms_to: str = "",
    error_msg: str = "",
) -> None:
    """Spara SMS-status i Supabase om spårningskolumnerna finns. Fel får aldrig stoppa orderflödet."""
    if not _supabase_client:
        return
    patch = {
        "sms_status": status,
        "sms_to": sms_to or "",
        "sms_last_error": (error_msg or "")[:500],
    }
    if status == "sent":
        patch["sms_sent_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    try:
        q = _supabase_client.table("orders").update(patch)
        if db_order_id:
            q = q.eq("id", db_order_id)
        elif order_id:
            q = q.eq("order_id", order_id)
        else:
            return
        q.execute()
    except Exception as e:
        print("⚠️  Supabase SMS status update skipped: %s" % e)


def _run_sms_and_alert_on_failure(
    order_dict: dict,
    customer_phone: Optional[str],
    rest_id: str,
    db_order_id: Optional[str] = None,
) -> None:
    """Körs i bakgrunden: skicka SMS; vid fel skicka alert till admin. Tar order som dict (order.model_dump())."""
    try:
        order = Order.model_validate(order_dict)
    except Exception as e:
        print("⚠️  Background SMS: kunde inte bygga Order från dict: %s" % e)
        _send_sms_failure_alert(rest_id, order_dict.get("order_id", "?"), str(e))
        return
    result = _send_sms_order_confirmation_result(order, customer_phone or "")
    if result["ok"]:
        _update_order_sms_status(db_order_id, order.order_id, "sent", result.get("to", ""), "")
        return
    error_msg = result.get("error") or "Vonage returnerade fel eller ingen telefon"
    status = "missing_phone" if error_msg == "missing_or_invalid_customer_phone" else "failed"
    if error_msg == "blocked_business_or_provider_number":
        status = "blocked_recipient"
    _update_order_sms_status(db_order_id, order.order_id, status, result.get("to", ""), error_msg)
    _send_sms_failure_alert(rest_id, order.order_id, error_msg)
    # Vid transient fel: lägg jobb i kön så ops-agenten kan retrya autonomt.
    is_permanent = error_msg in ("missing_or_invalid_customer_phone", "blocked_business_or_provider_number")
    if not is_permanent:
        try:
            rest_uuid = None
            if rest_id and rest_id in _CONFIG_CACHE:
                rest_uuid = _CONFIG_CACHE[rest_id].get("restaurant_uuid")
            ops_agent.queue_sms_job(
                _supabase_client,
                restaurant_uuid=rest_uuid,
                restaurant_id=rest_id,
                order_id=order.order_id,
                db_order_id=db_order_id,
                to_number=customer_phone or "",
                body=_format_order_sms(order),
            )
        except Exception as e:
            print(f"⚠️  queue_sms_job after failure soft-fail: {e}")


def send_customer_sms_now(
    order: Order,
    customer_phone: Optional[str],
    rest_id: str,
    db_order_id: Optional[str] = None,
) -> None:
    """Skicka SMS synkront (samma HTTP-request som ordern). Bakgrundstasker kan annars hinner inte köras klart."""
    _run_sms_and_alert_on_failure(order.model_dump(), customer_phone, rest_id, db_order_id)


def _token_bucket_allow(rest_id: str) -> bool:
    """Returnera True om anrop ska tillåtas (token bucket). Fas 2: per-tenant-parametrar från config-cache."""
    now = time.time()
    bucket_size = _TOKEN_BUCKET_DEFAULT_SIZE
    refill_per_sec = _TOKEN_BUCKET_DEFAULT_REFILL_PER_SEC
    if rest_id in _CONFIG_CACHE:
        entry = _CONFIG_CACHE[rest_id]
        bucket_size = entry.get("throttle_bucket_size", bucket_size)
        refill_per_sec = entry.get("throttle_refill_per_sec", refill_per_sec)
    try:
        bucket_size = max(1, int(bucket_size))
    except (TypeError, ValueError):
        bucket_size = _TOKEN_BUCKET_DEFAULT_SIZE
    try:
        refill_per_sec = max(0.01, float(refill_per_sec))
    except (TypeError, ValueError):
        refill_per_sec = _TOKEN_BUCKET_DEFAULT_REFILL_PER_SEC
    if rest_id not in _TOKEN_BUCKET:
        _TOKEN_BUCKET[rest_id] = {"tokens": bucket_size, "last_ts": now}
    entry = _TOKEN_BUCKET[rest_id]
    refill = (now - entry["last_ts"]) * refill_per_sec
    entry["tokens"] = min(bucket_size, entry["tokens"] + refill)
    entry["last_ts"] = now
    if entry["tokens"] >= 1:
        entry["tokens"] -= 1
        return True
    return False


def _invalidate_tenant_caches(rest_id: str) -> None:
    """Rensa config-cache, call_id-cache, circuit breaker och token bucket för denna tenant (Instant Kill).
    Tar omedelbart bort UUID från aktiva-set. Rensar minne för borttagna tenants."""
    uuid_to_remove = None
    if rest_id in _CONFIG_CACHE:
        uuid_to_remove = _CONFIG_CACHE[rest_id].get("restaurant_uuid")
        del _CONFIG_CACHE[rest_id]
    to_del = [cid for cid, v in _CALL_RESTAURANT_CACHE.items() if v.get("restaurant_id") == rest_id]
    for cid in to_del:
        del _CALL_RESTAURANT_CACHE[cid]
    if rest_id in _CIRCUIT_BREAKER:
        del _CIRCUIT_BREAKER[rest_id]
    if rest_id in _TOKEN_BUCKET:
        del _TOKEN_BUCKET[rest_id]
    if not uuid_to_remove and _supabase_client:
        try:
            r = _supabase_client.table("restaurants").select("id").eq("external_id", rest_id).limit(1).execute()
            if r.data and len(r.data) > 0:
                uuid_to_remove = str(r.data[0]["id"])
        except Exception:
            pass
    if uuid_to_remove:
        _ACTIVE_TENANT_UUIDS.discard(str(uuid_to_remove))
    global _ACTIVE_TENANT_LAST_REFRESH
    _ACTIVE_TENANT_LAST_REFRESH = 0


# ==================== API ENDPOINTS ====================

@app.get("/debug-vonage")
async def debug_vonage():
    """DEBUG: Kontrollera om Vonage env-variabler är satta (visar inte värden)."""
    return {
        "VONAGE_API_KEY": "SET" if VONAGE_API_KEY else "MISSING",
        "VONAGE_API_SECRET": "SET" if VONAGE_API_SECRET else "MISSING",
        "VONAGE_FROM_NUMBER": "SET" if VONAGE_FROM_NUMBER else "MISSING",
    }

@app.get("/debug-supabase")
async def debug_supabase():
    """DEBUG: Kontrollera om Supabase är konfigurerad på denna deployment (Railway)."""
    return {
        "SUPABASE_URL": "SET" if SUPABASE_URL else "MISSING",
        "SUPABASE_KEY": "SET" if SUPABASE_KEY else "MISSING",
        "RESTAURANT_UUID": "SET" if RESTAURANT_UUID else "MISSING",
        "client_initialized": _supabase_client is not None,
        "message": "OK – insert till orders ska fungera"
        if _supabase_client and RESTAURANT_UUID
        else "FEL – Supabase-insert skippas (saknad URL/KEY eller RESTAURANT_UUID)",
    }


@app.get("/debug-tenant")
async def debug_tenant(request: Request):
    """DEBUG: Verifiera tenant-lookup. Anrop med ?rest_id=Gislegrillen_01 (eller annat external_id)."""
    rest_id = request.query_params.get("rest_id") or "Gislegrillen_01"
    restaurant_id, restaurant_uuid = _get_restaurant_from_webhook({"rest_id": rest_id}, request)
    return {
        "rest_id_requested": rest_id,
        "restaurant_id": restaurant_id,
        "restaurant_uuid": restaurant_uuid,
        "lookup_ok": _supabase_client is not None and restaurant_uuid is not None,
    }


@app.get("/debug-call-cache")
async def debug_call_cache():
    """DEBUG: Antal call_id → restaurant som finns i cache (TTL 1h)."""
    now = time.time()
    valid = sum(1 for v in _CALL_RESTAURANT_CACHE.values() if (now - v["ts"]) <= _CALL_CACHE_TTL_SEC)
    return {"cache_size": len(_CALL_RESTAURANT_CACHE), "entries_within_ttl": valid}

@app.get("/")
async def root():
    """Root endpoint - API info"""
    return {
        "name": "Gislegrillen Voice AI Order System",
        "status": "operational",
        "version": "1.0.0",
        "endpoints": {
            "menu": "/menu",
            "orders": "/orders",
            "place_order": "/place_order",
            "dashboard": "/dashboard",
            "keywords": "/api/keywords"
        }
    }

@app.get("/menu")
async def get_menu(rest_id: Optional[str] = None):
    """Get full menu (cached 3 min). Optional rest_id for future per-tenant menu."""
    menu = get_menu_cached(rest_id)
    return JSONResponse(content=menu)


@app.post("/match_menu")
async def match_menu(request: Request, rest_id: Optional[str] = None):
    """Read-only menu matching. Validates item names against the menu without creating an order."""
    rest_id = (rest_id or "").strip() or "Gislegrillen_01"
    body = await request.json()
    raw_items = body.get("items")
    if not isinstance(raw_items, list) or len(raw_items) == 0:
        return JSONResponse(
            status_code=400,
            content={"error": "Request body must contain a non-empty 'items' array."},
        )

    menu = get_menu_cached(rest_id)
    index = menu_match.get_or_build_menu_index(rest_id, menu)
    if index is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Menyn kunde inte laddas."},
        )

    matched: list = []
    ambiguous: list = []
    unmatched: list = []

    for i, entry in enumerate(raw_items):
        name_in = ""
        if isinstance(entry, dict):
            name_in = (entry.get("name") or entry.get("raw") or "").strip()
        elif isinstance(entry, str):
            name_in = entry.strip()
        if not name_in:
            unmatched.append({"index": i, "input": ""})
            continue

        m = index.match_one(name_in, rest_id)
        mt = m.get("type")

        if mt in ("exact", "alias", "fuzzy_auto"):
            item_id = m["itemId"]
            menu_item = find_menu_item(item_id, rest_id)
            price = menu_item["price"] if menu_item else None
            confidence = 1.0 if mt in ("exact", "alias") else round(m.get("score", 0.0), 4)
            matched.append({
                "index": i,
                "input": name_in,
                "menuId": item_id,
                "menuName": m["canonicalName"],
                "price": price,
                "matchType": mt,
                "confidence": confidence,
            })
        elif mt == "fuzzy_ambiguous":
            ambiguous.append({
                "index": i,
                "input": name_in,
                "candidates": m.get("suggestions", []),
                "scores": m.get("scores", []),
            })
        else:
            unmatched.append({"index": i, "input": name_in})

    return JSONResponse(content={
        "matchedItems": matched,
        "ambiguousItems": ambiguous,
        "unmatchedItems": unmatched,
    })


def _sanitize_keyword(s: str, max_len: int = 50) -> str:
    """Tillåt bokstaver (åäö), siffror, mellanslag, bindestreck, apostrof, parenteser. Truncera till max_len."""
    # Behåll \w (bokstaver/siffror), \s, samt - ' ( ) så att "Ciao-Ciao", "Pizza (stor)" osv. behålls
    s = re.sub(r"[^\w\s\-'()]", " ", s, flags=re.UNICODE)
    s = " ".join(s.split()).strip()[:max_len]
    return s


@app.get("/api/keywords")
async def get_keywords(rest_id: Optional[str] = None, limit: Optional[int] = 100):
    """
    Return product names as keywords/keyterms for Vapi/Speechmatics keyword boosting.
    - keywords: single words (sanitized, max 50 chars)
    - keyterms: full product names as phrases (sanitized, max 50 chars).
    Optional rest_id for future per-tenant menu.
    """
    # Deepgram/Vapi brukar ha hårda gränser per request; defaulta till 100 så detta blir copy/paste.
    try:
        lim = int(limit) if limit is not None else 100
    except Exception:
        lim = 100
    lim = max(1, min(lim, 500))

    # Håll stopwords konservativt: ta bort konnektorer, men INTE matord som "mos/pommes".
    stopwords = {
        "och",
        "med",
        "i",
        "en",
        "ett",
        "tillagg",
        "tillägg",
    }

    menu = get_menu_cached(rest_id)
    keyterms_set = set()
    words_set = set()
    for category in menu.values():
        if not isinstance(category, list):
            continue
        for item in category:
            name = (item.get("name") or "").strip()
            if not name:
                continue
            term = _sanitize_keyword(name)
            if term:
                keyterms_set.add(term)
            for word in name.split():
                w = _sanitize_keyword(word.strip())
                if not w:
                    continue
                wl = w.lower()
                if len(wl) <= 1:
                    continue
                if wl in stopwords:
                    continue
                words_set.add(w)
            # Ta gärna med aliases också för STT-boost (t.ex. capriciosa/capricciosa)
            aliases = item.get("aliases")
            if isinstance(aliases, list):
                for a in aliases:
                    if not isinstance(a, str):
                        continue
                    aw = _sanitize_keyword(a.strip())
                    if aw and len(aw) > 1:
                        words_set.add(aw)

    keyterms = sorted(keyterms_set)[:lim]
    keywords = sorted(words_set)[:lim]
    return JSONResponse(content={"keywords": keywords, "keyterms": keyterms})

@app.get("/orders")
async def get_orders(rest_id: Optional[str] = None):
    """
    Visa ordrar för en tenant.

    Default-källa: Supabase (samma data som Lovable/KDS ser). Detta gör att
    ägaren aldrig hamnar i ett split brain-scenario där lokal dashboard visar
    annan data än Lovable.

    Vid Supabase-fel: vi loggar incident och faller tillbaka till orders.json
    så det lokala köks-skärmflödet inte dör mitt i en lunchrush.
    """
    rest_id_q = (rest_id or DEFAULT_DASHBOARD_REST_ID or "").strip()
    if DASHBOARD_FROM_DB and _supabase_client:
        rest_uuid: Optional[str] = None
        try:
            if rest_id_q:
                _, rest_uuid = _resolve_restaurant_by_external_id(rest_id_q)
        except Exception:
            rest_uuid = None
        rows, err = order_service.fetch_orders(
            _supabase_client,
            restaurant_uuid=rest_uuid,
            restaurant_id=rest_id_q if not rest_uuid else None,
            limit=200,
        )
        if rows is not None:
            return JSONResponse(content=[order_service.shape_order_for_dashboard(r) for r in rows])
        if err:
            print(f"⚠️  /orders Supabase fail (fallback till orders.json): {err}")
            ops_agent.create_incident(
                _supabase_client,
                incident_type="dashboard_supabase_read_failed",
                severity="P2",
                summary="Lokal dashboard kunde inte läsa ordrar från Supabase – fallback till orders.json.",
                restaurant_uuid=rest_uuid,
                restaurant_id=rest_id_q,
                details={"error": err[:500]},
            )
    # Fallback / utvecklingsläge.
    orders = load_orders()
    return JSONResponse(content=orders)

def _extract_vapi_tool_calls(msg: dict) -> list:
    """
    Extrahera place_order-anrop från Vapi-format.
    Stödjer: toolCalls, toolCallList, toolWithToolCallList.
    DEDUPLICERAR – Vapi skickar ofta samma anrop i både toolCalls OCH toolCallList.
    Returnerar lista med (tool_call_id, params_dict).
    """
    seen_ids = set()
    out = []
    def _add_from_tc(tc):
        cid = tc.get("id", "unknown")
        if cid in seen_ids:
            return
        fn = tc.get("function") or tc
        name = fn.get("name") or tc.get("name")
        args = fn.get("arguments") or fn.get("parameters") or tc.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        # Acceptera place_order antingen med explicit name ELLER om params innehåller items (Vapi toolCallList kan sakna name)
        is_place_order = name == "place_order"
        if not is_place_order and isinstance(args, dict):
            items = args.get("items") or args.get("order", {}).get("items") or args.get("full_order", {}).get("items")
            if isinstance(items, list) and len(items) > 0:
                is_place_order = True
        if not is_place_order:
            return
        seen_ids.add(cid)
        out.append((cid, args))

    # Vapi skickar toolCalls (id, type, function.name, function.arguments)
    for tc in msg.get("toolCalls", []):
        _add_from_tc(tc)
    # toolCallList (nytt 2025)
    for tc in msg.get("toolCallList", []):
        _add_from_tc(tc)
    # Gammalt: toolWithToolCallList
    for t in msg.get("toolWithToolCallList", []):
        if t.get("name") != "place_order":
            continue
        tc = t.get("toolCall", {})
        cid = tc.get("id", "unknown")
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        params = tc.get("parameters", {})
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {}
        out.append((cid, params))
    return out


def _looks_like_place_order_params(body: dict) -> bool:
    """True när Vapi skickar function-tool payload direkt till endpointen utan message/tool-calls-envelope."""
    if not isinstance(body, dict) or "message" in body:
        return False
    candidates = [body]
    for key in ("parameters", "arguments", "order", "full_order"):
        val = body.get(key)
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except json.JSONDecodeError:
                val = None
        if isinstance(val, dict):
            candidates.append(val)
    for candidate in candidates:
        items = candidate.get("items")
        if not items and isinstance(candidate.get("order"), dict):
            items = candidate["order"].get("items")
        if not items and isinstance(candidate.get("full_order"), dict):
            items = candidate["full_order"].get("items")
        if isinstance(items, list):
            return True
    return False


def _params_from_direct_place_order_payload(body: dict) -> dict:
    """Normalisera Vapi direct tool payload till samma params-format som tool-calls."""
    if not isinstance(body, dict):
        return {}
    for key in ("parameters", "arguments"):
        val = body.get(key)
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except json.JSONDecodeError:
                val = {}
        if isinstance(val, dict) and (
            val.get("items")
            or (isinstance(val.get("order"), dict) and val["order"].get("items"))
            or (isinstance(val.get("full_order"), dict) and val["full_order"].get("items"))
        ):
            return val
    return body


def _response_for_direct_place_order_result(result: dict) -> JSONResponse:
    """Vapi direct function tools läser response body som tool-resultat; håll formen enkel och JSON-baserad."""
    raw = result.get("result")
    if isinstance(raw, str):
        try:
            return JSONResponse(content=json.loads(raw))
        except json.JSONDecodeError:
            return JSONResponse(content={"success": False, "error": raw})
    if isinstance(raw, dict):
        return JSONResponse(content=raw)
    return JSONResponse(content={"success": False, "error": "Okänt orderresultat"})


def _handle_place_order_params(
    params: dict,
    body: dict,
    request: Optional[Request],
    rest_id: str,
    restaurant_id: str,
    restaurant_uuid: Optional[str],
    tool_call_id: str = "direct-place-order",
) -> dict:
    """
    Gemensam orderhantering för Vapi tool-calls och direct function-tool payloads.

    Skyddar mot:
      * Tappad/dubblerad order – idempotency via Supabase.
      * Falsk bekräftelse – success returneras endast efter DB-commit (i produktion).
      * Fel rätt – id/name invariant och fuzzy_auto markerar needs_review.
      * Pausad tenant – om ops-agent har pausat intake, neka mjukt.
    """
    customer_phone = _resolve_customer_phone(body, params)
    items_data = _parse_items_from_params(params, rest_id)

    # Råvalidering – innan menymatchning.
    try:
        order_integrity.validate_raw_items(items_data)
    except order_integrity.ValidationError as ve:
        order_service.write_order_event(
            _supabase_client,
            event_type="order_rejected_validation",
            restaurant_uuid=restaurant_uuid,
            restaurant_id=restaurant_id,
            order_id=None,
            correlation_id=_get_call_id_from_webhook(body),
            payload={"error_code": ve.error_code, "details": ve.details},
        )
        return {
            "name": "place_order",
            "toolCallId": tool_call_id,
            "result": menu_match.place_order_fail_json(ve.message, []),
        }

    # Tenant pausad?
    paused, paused_reason = ops_agent.is_intake_paused(_supabase_client, restaurant_uuid)
    if paused:
        ops_agent.create_incident(
            _supabase_client,
            incident_type="intake_paused_blocked_order",
            severity="P1",
            summary=f"Order avvisad pga pausad tenant ({paused_reason}).",
            restaurant_uuid=restaurant_uuid,
            restaurant_id=restaurant_id,
            human_required=True,
        )
        return {
            "name": "place_order",
            "toolCallId": tool_call_id,
            "result": menu_match.place_order_fail_json(
                "Beställningar kan inte tas emot just nu. Försök igen lite senare.",
                [],
            ),
        }

    rk, resolved_items, fail_json = _resolve_items_with_menu_match(items_data, rest_id)
    if not rk:
        order_service.write_order_event(
            _supabase_client,
            event_type="order_rejected_menu_match",
            restaurant_uuid=restaurant_uuid,
            restaurant_id=restaurant_id,
            order_id=None,
            correlation_id=_get_call_id_from_webhook(body),
            payload={"items_data": items_data},
        )
        return {
            "name": "place_order",
            "toolCallId": tool_call_id,
            "result": fail_json,
        }

    try:
        # Bygg OrderItem (Pydantic-validering kör här: quantity ge=1 le=MAX).
        items = []
        for it in resolved_items:
            items.append(OrderItem(
                id=it["id"],
                name=it["name"],
                quantity=it.get("quantity") or 1,
                price=it.get("price"),
                special_requests=it.get("special_requests"),
            ))
        customer_name = params.get("customer_name") or params.get("customerName") or ""
        raw_transcript = _get_raw_transcript_from_webhook(body)
        vapi_call_id = _get_call_id_from_webhook(body)
        draft_token = params.get("draft_token") or params.get("draftToken")
        commit = _commit_order_supabase_first(
            items=items,
            raw_items=resolved_items,
            rest_id=rest_id,
            restaurant_id=restaurant_id,
            restaurant_uuid=restaurant_uuid,
            customer_name=customer_name,
            customer_phone=customer_phone,
            raw_transcript=raw_transcript,
            special_requests=params.get("special_requests"),
            vapi_call_id=vapi_call_id,
            vapi_tool_call_id=tool_call_id if tool_call_id != "direct-place-order" else None,
            correlation_id=vapi_call_id,
            draft_token=draft_token if isinstance(draft_token, str) else None,
            require_draft_token=REQUIRE_DRAFT_TOKEN,
        )

        if not commit["success"]:
            print(f"❌ place_order commit failed: {commit.get('error_code')} {commit.get('error_message')}")
            if _circuit_breaker_record_failure(rest_id):
                _send_circuit_breaker_alert(rest_id)
            return {
                "name": "place_order",
                "toolCallId": tool_call_id,
                "result": menu_match.place_order_fail_json(
                    commit.get("error_message") or "Beställningen kunde inte genomföras. Försök igen.",
                    [],
                ),
            }

        _circuit_breaker_record_success(rest_id)
        order_id = commit["order_id"]
        total_price = commit["total_price"]
        needs_review = bool(commit.get("needs_human_review"))
        idempotent_replay = bool(commit.get("idempotent_replay"))
        # Bygg minimal "order"-objekt för SMS-flödet (vi har redan committed).
        sms_payload_order = Order(
            order_id=order_id,
            items=items,
            special_requests=params.get("special_requests"),
            total_price=total_price or 0.0,
            status="needs_review" if needs_review else "pending",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            needs_human_review=needs_review,
        )
        # SMS hoppas över för replays och needs_review (ingen falsk bekräftelse om köket inte godkänt).
        if not idempotent_replay and not needs_review:
            if customer_phone:
                send_customer_sms_now(sms_payload_order, customer_phone, rest_id, commit.get("db_order_id"))
            else:
                _update_order_sms_status(commit.get("db_order_id"), order_id, "missing_phone")
                print("⚠️  Ingen kundtelefon i place_order – SMS till kund skickades inte")
                ops_agent.create_incident(
                    _supabase_client,
                    incident_type="sms_missing_customer_phone",
                    severity="P2",
                    summary=(
                        f"Order {order_id} sparad utan SMS – inget kundnummer i Vapi/webhook. "
                        "Be AI skicka customer_phone eller fixa Vonage caller-ID."
                    ),
                    restaurant_uuid=restaurant_uuid,
                    restaurant_id=restaurant_id,
                    correlation_id=vapi_call_id,
                    vapi_call_id=vapi_call_id,
                    order_id=order_id,
                    human_required=False,
                )
        elif needs_review:
            ops_agent.create_incident(
                _supabase_client,
                incident_type="order_needs_human_review",
                severity="P1",
                summary=f"Order {order_id} kräver mänsklig granskning innan SMS/leverans.",
                restaurant_uuid=restaurant_uuid,
                restaurant_id=restaurant_id,
                correlation_id=vapi_call_id,
                vapi_call_id=vapi_call_id,
                order_id=order_id,
                human_required=True,
                details={"low_confidence": True},
            )

        result_payload = {
            "success": True,
            "order_id": order_id,
            "total_price": float(total_price or 0.0),
            "needs_human_review": needs_review,
        }
        if idempotent_replay:
            result_payload["idempotent_replay"] = True
        return {
            "name": "place_order",
            "toolCallId": tool_call_id,
            "result": json.dumps(result_payload, ensure_ascii=False),
        }
    except Exception as e:
        print(f"❌ place_order exception: {e}")
        if _circuit_breaker_record_failure(rest_id):
            _send_circuit_breaker_alert(rest_id)
        ops_agent.create_incident(
            _supabase_client,
            incident_type="place_order_exception",
            severity="P1",
            summary=f"Oväntat fel i place_order: {str(e)[:200]}",
            restaurant_uuid=restaurant_uuid,
            restaurant_id=restaurant_id,
            human_required=False,
        )
        return {
            "name": "place_order",
            "toolCallId": tool_call_id,
            "result": menu_match.place_order_fail_json(
                "Beställningen kunde inte genomföras. Försök igen.",
                [],
            ),
        }


def _process_place_order(
    items: List[OrderItem],
    special_requests: Optional[str] = None,
    rest_id: Optional[str] = None,
) -> Order:
    """Process order: validate, save, print köksbong. rest_id = vilken pizzeria (meny + priser)."""
    enriched_items = []
    per_item_specs = []
    for item in items:
        menu_item = find_menu_item(item.id, rest_id)
        if not menu_item:
            raise HTTPException(
                status_code=404,
                detail="Menu item with ID %s not found" % item.id,
            )
        name = menu_item["name"]
        enriched_items.append(OrderItem(
            id=item.id,
            name=name,
            quantity=item.quantity,
            price=menu_item["price"],
            special_requests=item.special_requests,
        ))
        if item.special_requests and item.special_requests.strip():
            per_item_specs.append("%dx %s: %s" % (item.quantity, name, item.special_requests.strip()))
    combined_special = "; ".join(per_item_specs) if per_item_specs else special_requests
    total_price = calculate_total_price(enriched_items, rest_id)
    order = Order(
        order_id=generate_order_id(),
        items=enriched_items,
        special_requests=combined_special,
        total_price=total_price,
        status="pending",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    orders = load_orders()
    orders.append(order.model_dump())
    save_orders(orders)
    print_kitchen_ticket(order)
    return order


@app.post("/draft_order")
async def draft_order(request: Request):
    """
    Returnera canonical readback för en beställning UTAN att committa något.

    AI-flödet:
      1. Vapi anropar /draft_order med items + special_requests.
      2. Backend kör menymatchning, validering och bygger canonical payload.
      3. Backend signerar en draft_token (HMAC) med payload_hash + restaurant_uuid.
      4. AI läser upp canonical_items + total för kunden och frågar om bekräftelse.
      5. Vid ja: AI anropar /place_order med draft_token. Backend verifierar att
         items fortfarande hashar till samma värde innan commit.

    Detta hindrar AI från att lova pickup-tid eller bekräfta beställning innan
    backend faktiskt godkänt och committat ordern.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"success": False, "error": "Ogiltig JSON-body."}, status_code=400)

    rest_id = (
        (request.query_params.get("rest_id") or "").strip()
        or (body or {}).get("rest_id")
        or DEFAULT_DASHBOARD_REST_ID
    )
    if not _circuit_breaker_allow(rest_id):
        return JSONResponse(content={"success": False, "error": "Temporärt fel. Försök igen om en minut."})
    if not _token_bucket_allow(rest_id):
        return JSONResponse(content={"success": False, "error": "För många anrop. Vänta en stund."})
    restaurant_id, restaurant_uuid = _get_restaurant_config_cached(body, request)
    if restaurant_id is None and restaurant_uuid is None:
        return JSONResponse(content={"success": False, "error": "Restaurangen kunde inte hittas."})

    paused, reason = ops_agent.is_intake_paused(_supabase_client, restaurant_uuid)
    if paused:
        return JSONResponse(content={
            "success": False,
            "error": "Beställningar pausade just nu. Försök igen senare.",
            "reason": reason,
        })

    items_data = _parse_items_from_params(body, rest_id)
    try:
        order_integrity.validate_raw_items(items_data)
    except order_integrity.ValidationError as ve:
        return JSONResponse(content={
            "success": False,
            "error": ve.message,
            "error_code": ve.error_code,
            "details": ve.details,
        })

    rk, resolved_items, fail_json = _resolve_items_with_menu_match(items_data, rest_id)
    if not rk:
        try:
            payload = json.loads(fail_json)
        except Exception:
            payload = {"success": False, "error": "Menymatchning misslyckades."}
        return JSONResponse(content=payload)

    items = []
    for it in resolved_items:
        items.append(OrderItem(
            id=it["id"],
            name=it["name"],
            quantity=it.get("quantity") or 1,
            price=it.get("price"),
            special_requests=it.get("special_requests"),
        ))
    draft = _build_draft_for_items(
        items=items,
        raw_items=resolved_items,
        restaurant_uuid=restaurant_uuid,
        special_requests=body.get("special_requests") if isinstance(body, dict) else None,
    )
    return JSONResponse(content={
        "success": True,
        "canonical_items": draft["canonical_items"],
        "total_price": draft["total_price"],
        "payload_hash": draft["payload_hash"],
        "draft_token": draft["draft_token"],
        "expires_at": draft["expires_at"],
        "needs_human_review": draft["needs_human_review"],
        "low_confidence_rows": draft["low_confidence_rows"],
        "readback": draft["readback"],
    })


@app.post("/place_order")
async def place_order(request: Request):
    """
    Main order placement endpoint - Called by Vapi tool OR direct API.
    Supports both Vapi tool-calls format and direct JSON format.
    OBS: Om Vapi-place_order har egen Server URL går tool-calls HIT, inte till /vapi/webhook.
    """
    try:
        body = await request.json()
        print("\n!!! PLACE_ORDER ENDPOINT HIT !!! (Vapi skickar tool-calls hit om tool har egen URL)")
        print("="*50)
        print("📥 PLACE_ORDER ANROPAD! (från Vapi Tool URL eller direkt)")
        print("="*50)
        print(f"DEBUG: body keys={list(body.keys())}")
        if isinstance(body.get("message"), dict):
            m = body["message"]
            print(f"DEBUG: body.message keys={list(m.keys())}, has call={bool(m.get('call'))}")
            if m.get("call"):
                print(f"DEBUG: body.message.call keys={list(m['call'].keys())}, has customer={bool(m['call'].get('customer'))}")
        print(f"Body (första 800 tecken): {json.dumps(body, indent=2, ensure_ascii=False)[:800]}")

        # Vapi tool-calls format: toolCallList (nytt) eller toolWithToolCallList (gammalt)
        if "message" in body and isinstance(body.get("message"), dict):
            msg = body["message"]
            has_tools = msg.get("toolCalls") or msg.get("toolCallList") or msg.get("toolWithToolCallList")
            if (msg.get("type") == "tool-calls" or has_tools) and has_tools:
                # Fas 1: rest_id, circuit breaker, token bucket, config-cache
                rest_id = _get_rest_id_from_request(request, body)
                call_id = _get_call_id_from_webhook(body)
                if not rest_id and call_id and call_id in _CALL_RESTAURANT_CACHE:
                    rest_id = _CALL_RESTAURANT_CACHE[call_id].get("restaurant_id") or rest_id
                rest_id = rest_id or "Gislegrillen_01"
                if not _circuit_breaker_allow(rest_id):
                    return JSONResponse(content={"results": [{"error": "Temporärt fel. Försök igen om en minut."}]}, status_code=200)
                if not _token_bucket_allow(rest_id):
                    return JSONResponse(content={"results": [{"error": "För många anrop. Vänta en stund."}]}, status_code=200)
                restaurant_id, restaurant_uuid = _get_restaurant_config_cached(body, request)
                if restaurant_id is None and restaurant_uuid is None:
                    return JSONResponse(content={"results": [{"error": "Restaurangen kunde inte hittas."}]}, status_code=200)
                if call_id:
                    _cache_restaurant_for_call(call_id, restaurant_id, restaurant_uuid)
                calls = _extract_vapi_tool_calls(msg)
                results = []
                for tool_call_id, params in calls:
                    results.append(
                        _handle_place_order_params(
                            params,
                            body,
                            request,
                            rest_id,
                            restaurant_id,
                            restaurant_uuid,
                            tool_call_id=tool_call_id,
                        )
                    )
                if results:
                    print(f"✅ Vapi tool-call processed, {len(results)} result(s)")
                    return JSONResponse(content={"results": results})
                print("⚠️  Body hade message/toolCalls men INGEN place_order hittades – kolla format!")
                raise HTTPException(status_code=400, detail="No place_order tool call found")
        
        # Direct format: {"items": [...], "special_requests": "..."}
        # Samma orderflöde som Vapi: menyvalidering, Supabase och SMS-status. Optional ?rest_id=.
        rest_direct = (request.query_params.get("rest_id") or "").strip() or "Gislegrillen_01"
        if not _circuit_breaker_allow(rest_direct):
            return JSONResponse(content={"success": False, "error": "Temporärt fel. Försök igen om en minut."})
        if not _token_bucket_allow(rest_direct):
            return JSONResponse(content={"success": False, "error": "För många anrop. Vänta en stund."})
        restaurant_id, restaurant_uuid = _get_restaurant_config_cached(body, request)
        if restaurant_id is None and restaurant_uuid is None:
            return JSONResponse(content={"success": False, "error": "Restaurangen kunde inte hittas."})
        params = _params_from_direct_place_order_payload(body)
        result = _handle_place_order_params(
            params,
            body,
            request,
            rest_direct,
            restaurant_id,
            restaurant_uuid,
        )
        return _response_for_direct_place_order_result(result)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error placing order: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update_order_status")
async def update_order_status(request: UpdateOrderStatusRequest, rest_id: Optional[str] = None):
    """
    Uppdatera orderstatus. Pydantic har redan validerat att status är tillåten.

    Default-källa: Supabase. Detta gör att samma update slår igenom mot Lovable/KDS.
    Vi uppdaterar även orders.json som backup.
    """
    try:
        rest_id_q = (rest_id or DEFAULT_DASHBOARD_REST_ID or "").strip()
        rest_uuid: Optional[str] = None
        if rest_id_q:
            try:
                _, rest_uuid = _resolve_restaurant_by_external_id(rest_id_q)
            except Exception:
                rest_uuid = None

        db_ok = False
        db_err: Optional[str] = None
        if DASHBOARD_FROM_DB and _supabase_client:
            db_ok, db_err = order_service.update_order_status(
                _supabase_client,
                order_id=request.order_id,
                new_status=request.status,
                restaurant_uuid=rest_uuid,
                restaurant_id=rest_id_q if not rest_uuid else None,
            )
            if db_ok:
                order_service.write_order_event(
                    _supabase_client,
                    event_type="status_changed",
                    restaurant_uuid=rest_uuid,
                    restaurant_id=rest_id_q,
                    order_id=request.order_id,
                    correlation_id=None,
                    payload={"new_status": request.status},
                )
            else:
                print(f"⚠️  /update_order_status Supabase fail: {db_err}")

        orders = load_orders()
        order_found = False
        for order in orders:
            if order.get("order_id") == request.order_id:
                order["status"] = request.status
                order_found = True
                break
        if order_found:
            save_orders(orders)

        if not db_ok and not order_found:
            raise HTTPException(status_code=404, detail="Order not found")

        print(f"✅ Order {request.order_id} status -> {request.status} (db_ok={db_ok}, json_ok={order_found})")
        return JSONResponse(content={
            "success": True,
            "message": f"Order status updated to {request.status}",
            "supabase_updated": db_ok,
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error updating order status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve kitchen dashboard HTML"""
    dashboard_file = BASE_DIR / "index.html"
    try:
        with open(dashboard_file, 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Dashboard not found. Please create index.html</h1>",
            status_code=404
        )

@app.get("/system_prompt")
async def get_system_prompt():
    """Get system prompt for Vapi configuration"""
    try:
        with open(SYSTEM_PROMPT_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        return JSONResponse(content={
            "system_prompt": content,
            "file": str(SYSTEM_PROMPT_FILE)
        })
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="System prompt file not found")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse(content={
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "vapi_configured": bool(VAPI_API_KEY),
            "supabase_configured": bool(_supabase_client),
            "vonage_sms_configured": bool(VONAGE_API_KEY and VONAGE_API_SECRET and VONAGE_FROM_NUMBER),
            "sms_tracking_enabled": True,
            "vonage_request_encoding": "form_urlencoded",
        }
    })

# ==================== FAS 1: ADMIN (Instant Kill) ====================

@app.post("/admin/menu/invalidate")
async def admin_invalidate_menu(request: Request, rest_id: Optional[str] = None):
    """
    Rensa meny-cache så nästa GET /menu och GET /api/keywords laddar från menu.json.
    Använd efter ändring av menu.json så du inte behöver vänta 3 min eller starta om.
    Kräver X-Admin-Key = ADMIN_SECRET. Optional ?rest_id= för att rensa bara den nyckeln.
    """
    key = request.headers.get("X-Admin-Key") or request.query_params.get("admin_key") or ""
    if not ADMIN_SECRET or key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    _invalidate_menu_cache(rest_id.strip() if rest_id else None)
    return {"ok": True, "message": "Menu cache invalidated", "rest_id": rest_id or "(all)"}


@app.post("/admin/tenants/{rest_id}/invalidate")
async def admin_invalidate_tenant(rest_id: str, request: Request):
    """
    Rensa config-cache och call_id-cache för denna tenant (Instant Kill).
    Kräver header X-Admin-Key eller ?admin_key= med värde ADMIN_SECRET.
    """
    key = request.headers.get("X-Admin-Key") or request.query_params.get("admin_key") or ""
    if not ADMIN_SECRET or key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    _invalidate_tenant_caches(rest_id.strip())
    return {"ok": True, "message": "Tenant caches invalidated", "rest_id": rest_id.strip()}


def _sms_sender_for_worker(to_number: str, body: str) -> Dict[str, Any]:
    """Wrapper som ops_worker kan använda för att skicka SMS via Vonage."""
    to = _normalize_phone_for_sms(to_number)
    if not to:
        return {"ok": False, "error": "missing_or_invalid_customer_phone"}
    if _is_blocked_sms_recipient(to):
        return {"ok": False, "error": "blocked_business_or_provider_number"}
    if not VONAGE_API_KEY or not VONAGE_API_SECRET or not VONAGE_FROM_NUMBER:
        return {"ok": False, "error": "vonage_not_configured"}
    try:
        r = requests.post(
            "https://rest.nexmo.com/sms/json",
            data={
                "api_key": VONAGE_API_KEY,
                "api_secret": VONAGE_API_SECRET,
                "from": VONAGE_FROM_NUMBER,
                "to": to,
                "text": body,
            },
            timeout=10,
        )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        msgs = data.get("messages") or []
        if msgs and msgs[0].get("status") == "0":
            return {"ok": True, "to": to}
        err = (msgs[0].get("error-text") if msgs else None) or r.text
        return {"ok": False, "error": str(err)[:300]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/admin/ops/run")
async def admin_ops_run(request: Request):
    """
    Kör en ops-tick: SMS retries, tenant health reconciliation, idempotency cleanup.
    Tänkt att triggas av Railway cron (var 60–120 sek) eller manuellt.
    Kräver X-Admin-Key = ADMIN_SECRET.
    """
    key = request.headers.get("X-Admin-Key") or request.query_params.get("admin_key") or ""
    if not ADMIN_SECRET or key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    summary = ops_worker.run_tick(_supabase_client, sms_sender=_sms_sender_for_worker)
    return {"ok": True, "summary": summary}


@app.get("/admin/ops/incidents")
async def admin_ops_incidents(request: Request, status: Optional[str] = None, limit: int = 50):
    """Visa öppna incidenter för operatören. Kräver X-Admin-Key."""
    key = request.headers.get("X-Admin-Key") or request.query_params.get("admin_key") or ""
    if not ADMIN_SECRET or key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not _supabase_client:
        return {"ok": True, "incidents": [], "note": "Supabase not configured"}
    try:
        q = _supabase_client.table("incidents").select("*").order("created_at", desc=True).limit(int(limit))
        if status:
            q = q.eq("status", status.strip())
        resp = q.execute()
        return {"ok": True, "incidents": getattr(resp, "data", None) or []}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/admin/tenants/{rest_id}/soft-delete")
async def admin_soft_delete_tenant(rest_id: str, request: Request):
    """
    Fas 3: Soft delete – (1) Instant Kill (invalidate), (2) sätt deleted_at = now() i DB.
    Tenant serveras inte längre; orders behålls. Kräver X-Admin-Key = ADMIN_SECRET.
    """
    key = request.headers.get("X-Admin-Key") or request.query_params.get("admin_key") or ""
    if not ADMIN_SECRET or key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    rest_id = rest_id.strip()
    _invalidate_tenant_caches(rest_id)
    if not _supabase_client:
        return {
            "ok": True,
            "message": "Tenant caches invalidated (Instant Kill). Supabase ej konfigurerad – deleted_at kunde inte sättas; sätt den manuellt i DB om du använder Fas 3.",
            "rest_id": rest_id,
        }
    try:
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        _supabase_client.table("restaurants").update({"deleted_at": ts}).eq("external_id", rest_id).execute()
    except Exception as e:
        err = str(e).lower()
        print("⚠️  Soft delete DB update failed: %s" % e)
        if "deleted_at" in err or "column" in err:
            raise HTTPException(status_code=400, detail="Kör supabase_fas3_deleted_at.sql i Supabase först (kolumn deleted_at saknas).")
        raise HTTPException(status_code=500, detail="DB update failed: " + str(e))
    return {"ok": True, "message": "Tenant soft-deleted (caches invalidated, deleted_at set)", "rest_id": rest_id}


# ==================== VAPI WEBHOOK ENDPOINTS ====================

@app.post("/vapi/webhook")
@app.post("/vapi-webhook")
async def vapi_webhook(request: Request):
    """
    Vapi webhook – tenant-blind, request-isolerad.
    - rest_id från query (?rest_id=...) eller body → lookup i Supabase restaurants → (restaurant_id, restaurant_uuid).
    - call_id (message.call.id) sparas tillsammans med restaurant i cache så att place_order alltid får rätt tenant (även vid separata anrop).
    - place_order använder _get_restaurant_for_webhook (cache eller lookup) och sparar order med rätt restaurant_uuid.
    - Request-isolering: vid alla undantag returneras 200 med säkert svar (ingen 500, ingen domino).
    """
    try:
        body = await request.json()
        print(f">>> RAW INCOMING: path=/vapi/webhook, content_length={request.headers.get('content-length')}, type={body.get('message', {}).get('type')}")
        print(f"FULL BODY KEYS: {json.dumps(list(body.keys()))}")
        print(f"MESSAGE TYPE: {body.get('message') and body['message'].get('type')}")

        msg = body.get("message", {})
        event_type = msg.get("type", "unknown")

        print("\n" + "-"*50)
        print(f"📞 VAPI WEBHOOK: event_type={event_type}")

        # Värm cache med kundnummer tidigt (status-update, assistant-started, etc.)
        # så place_order/tool-calls har numret även om payloaden är minimal.
        _early_call_id = _get_call_id_from_webhook(body)
        if _early_call_id and event_type not in ("end-of-call-report",):
            _resolve_customer_phone(body, None)

        # Vapi function tools can POST the tool arguments directly to the server URL.
        # Treat that as place_order instead of returning a generic success for an unknown event.
        if _looks_like_place_order_params(body):
            rest_id = _get_rest_id_from_request(request, body) or "Gislegrillen_01"
            if not _circuit_breaker_allow(rest_id):
                return JSONResponse(content={"success": False, "error": "Temporärt fel. Försök igen om en minut."})
            if not _token_bucket_allow(rest_id):
                return JSONResponse(content={"success": False, "error": "För många anrop. Vänta en stund."})
            restaurant_id, restaurant_uuid = _get_restaurant_config_cached(body, request)
            if restaurant_id is None and restaurant_uuid is None:
                return JSONResponse(content={"success": False, "error": "Restaurangen kunde inte hittas."})
            params = _params_from_direct_place_order_payload(body)
            result = _handle_place_order_params(
                params,
                body,
                request,
                rest_id,
                restaurant_id,
                restaurant_uuid,
            )
            return _response_for_direct_place_order_result(result)

        # Handle end-of-call-report
        # OBS: Vi skippar order-skapande här för att undvika DUBBLA ordrar.
        # tool-calls hanterar redan beställningen. end-of-call-report används bara som fallback
        # om tool-calls aldrig når oss (t.ex. avbruten samtal) – men då saknas ofta data.
        if event_type == "end-of-call-report":
            print("   (end-of-call-report: mottagen – order redan sparad via tool-calls)")
            return JSONResponse(content={"success": True, "event": "end-of-call-report"})

        # Handle tool-calls (stödjer toolCallList och toolWithToolCallList)
        if event_type == "tool-calls":
            # Fas 1: rest_id för circuit breaker och token bucket (från request/body eller call_id-cache)
            rest_id = _get_rest_id_from_request(request, body)
            call_id = _get_call_id_from_webhook(body)
            if not rest_id and call_id and call_id in _CALL_RESTAURANT_CACHE:
                rest_id = _CALL_RESTAURANT_CACHE[call_id].get("restaurant_id") or rest_id
            rest_id = rest_id or "Gislegrillen_01"
            if not _circuit_breaker_allow(rest_id):
                return JSONResponse(content={"results": [{"error": "Temporärt fel. Försök igen om en minut."}]}, status_code=200)
            if not _token_bucket_allow(rest_id):
                return JSONResponse(content={"results": [{"error": "För många anrop. Vänta en stund."}]}, status_code=200)
            restaurant_id, restaurant_uuid = _get_restaurant_config_cached(body, request)
            if restaurant_id is None and restaurant_uuid is None:
                return JSONResponse(content={"results": [{"error": "Restaurangen kunde inte hittas."}]}, status_code=200)
            if call_id:
                _cache_restaurant_for_call(call_id, restaurant_id, restaurant_uuid)
            # DEBUG: logga message.call struktur för att verifiera kundnummer-sökväg
            msg_struct = body.get("message") or {}
            call_data = msg_struct.get("call") or {}
            cust_data = call_data.get("customer") or msg_struct.get("customer") or {}
            print(f"DEBUG SMS: message.call keys={list(call_data.keys())}, customer keys={list(cust_data.keys())}")
            calls = _extract_vapi_tool_calls(msg)
            results = []
            for tool_call_id, params in calls:
                results.append(
                    _handle_place_order_params(
                        params,
                        body,
                        request,
                        rest_id,
                        restaurant_id,
                        restaurant_uuid,
                        tool_call_id=tool_call_id,
                    )
                )
            if results:
                return JSONResponse(content={"results": results})
        
        print(f"   Event: {event_type}")
        return JSONResponse(content={"success": True, "event": event_type})
        
    except Exception as e:
        print(f"❌ Vapi webhook error: {e}")
        # Request-isolering: returnera alltid 200 så att processen inte kraschar och Vapi inte retry:ar i oändlighet
        return JSONResponse(
            content={"success": False, "message": "Något gick fel. Försök igen."},
            status_code=200,
        )

# ==================== SERVER STARTUP ====================

def initialize_data_files():
    """Initialize data files if they don't exist"""
    if not ORDERS_FILE.exists():
        print(f"📝 Creating {ORDERS_FILE}")
        save_orders([])
    
    if not MENU_FILE.exists():
        print(f"⚠️  WARNING: {MENU_FILE} not found!")
    
    if not SYSTEM_PROMPT_FILE.exists():
        print(f"⚠️  WARNING: {SYSTEM_PROMPT_FILE} not found!")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🍕 GISLEGRILLEN VOICE AI ORDER SYSTEM 🍕".center(60))
    print("="*60)
    print(f"FastAPI Server Starting...")
    print(f"Host: {HOST}")
    print(f"Port: {PORT}")
    print(f"Dashboard: http://localhost:{PORT}/dashboard")
    print("="*60 + "\n")
    
    # Initialize data files
    initialize_data_files()
    
    # Check configuration
    if not VAPI_API_KEY:
        print("⚠️  WARNING: VAPI_API_KEY not configured!")
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️  Supabase not configured (KDS/Lovable) – orders will not sync to Supabase")
    # DEBUG: Vonage env vars vid start
    print(f"DEBUG VONAGE: VONAGE_API_KEY={'SET' if VONAGE_API_KEY else 'MISSING'}")
    print(f"DEBUG VONAGE: VONAGE_API_SECRET={'SET' if VONAGE_API_SECRET else 'MISSING'}")
    print(f"DEBUG VONAGE: VONAGE_FROM_NUMBER={'SET' if VONAGE_FROM_NUMBER else 'MISSING'}")
    print("\n✅ Server ready to accept orders!\n")
    
    # Run server
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info"
    )
