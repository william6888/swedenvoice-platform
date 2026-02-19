"""
Gislegrillen Voice AI Order System
FastAPI backend for Vapi.ai integration with Groq LLM
"""

import base64
import hashlib
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
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

# Configuration (måste vara före Supabase-init)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
# Multi-tenancy: UUID för denna restaurang (från public.restaurants). Sätts när Supabase har restaurant_uuid.
RESTAURANT_UUID = os.getenv("RESTAURANT_UUID", "").strip() or None

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
VAPI_API_KEY = os.getenv("VAPI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY", "")
PUSHOVER_API_TOKEN = os.getenv("PUSHOVER_API_TOKEN", "")
VONAGE_API_KEY = os.getenv("VONAGE_API_KEY", "")
VONAGE_API_SECRET = os.getenv("VONAGE_API_SECRET", "")
VONAGE_FROM_NUMBER = os.getenv("VONAGE_FROM_NUMBER", "")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
# Fas 1 Safety Net: admin-endpoint och alert
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "").strip()
PUSHOVER_ALERTS_USER_KEY = os.getenv("PUSHOVER_ALERTS_USER_KEY", PUSHOVER_USER_KEY or "").strip()
PUSHOVER_ALERTS_TOKEN = os.getenv("PUSHOVER_ALERTS_TOKEN", PUSHOVER_API_TOKEN or "").strip()

# Fas 2: Kryptering av tenant-nycklar (restaurant_secrets)
ENCRYPTION_SECRET = os.getenv("ENCRYPTION_SECRET", "").strip()
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

@app.middleware("http")
async def log_post_path(request: Request, call_next):
    """Logga POST till place_order/webhook – spåra var tool-calls går."""
    if request.method == "POST" and request.url.path in ("/place_order", "/vapi/webhook", "/vapi-webhook"):
        print(f">>> INCOMING POST {request.url.path} <<<")
    return await call_next(request)

@app.on_event("startup")
async def startup_debug():
    """DEBUG: Logga Vonage env vid app-start (körs också på Railway)."""
    print(f"DEBUG VONAGE: VONAGE_API_KEY={'SET' if VONAGE_API_KEY else 'MISSING'}")
    print(f"DEBUG VONAGE: VONAGE_API_SECRET={'SET' if VONAGE_API_SECRET else 'MISSING'}")
    print(f"DEBUG VONAGE: VONAGE_FROM_NUMBER={'SET' if VONAGE_FROM_NUMBER else 'MISSING'}")
    print(f"Fas 1: POST /admin/tenants/{{rest_id}}/invalidate (ADMIN_SECRET={'SET' if ADMIN_SECRET else 'MISSING'})")

# ==================== DATA MODELS ====================

class OrderItem(BaseModel):
    id: int
    name: str
    quantity: int
    price: Optional[float] = None
    special_requests: Optional[str] = None

class PlaceOrderRequest(BaseModel):
    items: List[OrderItem]
    special_requests: Optional[str] = None

class Order(BaseModel):
    order_id: str
    items: List[OrderItem]
    special_requests: Optional[str] = None
    total_price: float
    status: str
    timestamp: str

class UpdateOrderStatusRequest(BaseModel):
    order_id: str
    status: str

# ==================== FLOW REGISTRY (multi-tenant / unik logik) ====================
# Nya flöden: lägg till en handler-funktion och registrera här. Ingen if/else i webhook.
# Idag: bara "standard". Vid behov kan restaurants.flow_type eller restaurant_settings.flow_type styra vilken som anropas.
FLOW_HANDLERS = {"standard": None}  # None = nuvarande inline-logik; vid nytt flöde: def handle_xy(...): ... och FLOW_HANDLERS["xy"] = handle_xy


def get_flow_handler(flow_type: Optional[str] = None):
    """Returnerar handler för flow_type. Om okänd eller None används 'standard'."""
    key = (flow_type or "standard").strip().lower()
    return FLOW_HANDLERS.get(key, FLOW_HANDLERS["standard"])

# ==================== HELPER FUNCTIONS ====================

def _parse_items_from_params(params: dict) -> list:
    """Extrahera items från params – stödjer items, order.items, full_order.items, maträtter. Normaliserar itemId/qty."""
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
            mi = find_menu_item(int(d["id"]))
            d["name"] = mi["name"] if mi else f"Artikel {d['id']}"
        out.append(d)
    return out

def load_menu():
    """Load menu from JSON file"""
    try:
        with open(MENU_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ ERROR: {MENU_FILE} not found!")
        return {"pizzas": [], "kebabs": [], "burgers": [], "sides": [], "drinks": []}

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

def find_menu_item(item_id: int):
    """Find menu item by ID across all categories"""
    menu = load_menu()
    for category in menu.values():
        for item in category:
            if item.get('id') == item_id:
                return item
    return None

def calculate_total_price(items: List[OrderItem]) -> float:
    """Calculate total price from order items"""
    total = 0.0
    for item in items:
        menu_item = find_menu_item(item.id)
        if menu_item:
            total += menu_item['price'] * item.quantity
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

def send_pushover_notification(order: Order, customer_phone: Optional[str] = None):
    """Send push notification via Pushover API. Inkluderar kundens telefon om angiven."""
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        print("⚠️  Pushover credentials not configured. Skipping notification.")
        return False

    print(f"📤 Skickar Pushover-notis för order {order.order_id}... (customer_phone={customer_phone})")
    message = f"🔔 Ny beställning!\n\n"
    message += f"Order: {order.order_id}\n"
    message += f"Tid: {order.timestamp}\n"
    if customer_phone:
        message += f"Telefon: {customer_phone}\n"
    message += "\n"
    for item in order.items:
        message += f"• {item.quantity}x {item.name}\n"
    if order.special_requests:
        message += f"\n⚠️ Special: {order.special_requests}\n"
    message += f"\nTotalt: {order.total_price} kr"

    for attempt in range(2):
        try:
            response = requests.post(
                "https://api.pushover.net/1/messages.json",
                data={
                    "token": PUSHOVER_API_TOKEN,
                    "user": PUSHOVER_USER_KEY,
                    "title": "Gislegrillen - Ny Order",
                    "message": message,
                    "priority": 1,
                    "sound": "cashregister"
                },
                timeout=10
            )
            if response.status_code == 200:
                print("✅ Pushover notification sent successfully!")
                return True
            err = response.text
            print(f"⚠️  Pushover FAILED (HTTP {response.status_code}): {err}")
            try:
                err_json = response.json()
                if "errors" in err_json:
                    print(f"   Pushover errors: {err_json['errors']}")
                if "limit" in err.lower() or "rate" in err.lower():
                    print("   💡 Tip: Pushover har månadsgräns (10 000/mån). Kolla pushover.net")
            except Exception:
                pass
            if attempt == 0:
                time.sleep(1)
                continue
            return False
        except Exception as e:
            print(f"❌ Pushover-fel: {e}")
            if attempt == 0:
                time.sleep(1)
                continue
            return False
    return False


def _insert_order_to_supabase(
    order: Order,
    restaurant_id: str,
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
    raw_transcript: Optional[str] = None,
    restaurant_uuid: Optional[str] = None,
) -> bool:
    """Insert order to Supabase (orders-tabell för KDS/Lovable Dashboard). Returnerar True vid lyckad insert.
    restaurant_uuid: om None används RESTAURANT_UUID (bakåtkompat)."""
    if not _supabase_client:
        print("⚠️  Supabase insert SKIPPED: _supabase_client is None (SUPABASE_URL/SUPABASE_KEY saknas eller init misslyckades vid start)")
        return False
    try:
        items_json = [{"id": i.id, "name": i.name, "quantity": i.quantity, "price": i.price} for i in order.items]
        row = {
            "restaurant_id": restaurant_id or "default",
            "customer_name": customer_name or "",
            "customer_phone": customer_phone or "",
            "items": items_json,
            "total_price": float(order.total_price),
            "status": "NYA",
            "raw_transcript": raw_transcript or "",
        }
        uuid_val = restaurant_uuid or RESTAURANT_UUID
        if uuid_val:
            row["restaurant_uuid"] = uuid_val
        resp = _supabase_client.table("orders").insert(row).execute()
        # Detaljerad logg (Supabase AI-felsökning)
        err = getattr(resp, "error", None)
        data = getattr(resp, "data", None)
        status_code = getattr(resp, "status_code", None)
        auth_preview = "eyJ (JWT)" if SUPABASE_KEY and str(SUPABASE_KEY).strip().startswith("eyJ") else "annat"
        print(f"SUPABASE RESP: status_code={status_code} | data={data} | error={err}")
        if data is None and err is None:
            print(f"SUPABASE RAW resp type: {type(resp).__name__}, attrs: {[a for a in dir(resp) if not a.startswith('_')]}")
        print(f"SUPABASE AUTH: {auth_preview}")
        if err:
            print(f"⚠️  Supabase insert FAILED: {err}")
            return False
        print(f"✅ Order {order.order_id} sparad till Supabase (restaurant_id={restaurant_id})")
        return True
    except Exception as e:
        print(f"⚠️  Supabase insert failed: {e}")
        return False


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

def send_sms_order_confirmation(order: Order, to_number: str) -> bool:
    """
    Skicka SMS-orderbekräftelse via Vonage.
    Returnerar True vid lyckat skickande, False annars.
    Blockerar ALDRIG – fel loggas men kastas inte.
    """
    if not VONAGE_API_KEY or not VONAGE_API_SECRET or not VONAGE_FROM_NUMBER:
        print("⚠️  Vonage not configured. Skipping SMS.")
        return False
    print(f"DEBUG SMS: Vonage config OK, calling API for to_number={to_number}")
    if not to_number or not str(to_number).strip():
        print("⚠️  No customer phone number. Skipping SMS.")
        return False
    to = str(to_number).strip().replace(" ", "").replace("-", "")
    if not to.startswith("+"):
        to = ("+46" + to[1:]) if to.startswith("0") and len(to) > 1 else "+" + to
    text = _format_order_sms(order)
    try:
        r = requests.post(
            "https://rest.nexmo.com/sms/json",
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
            return True
        err = (msgs[0].get("error-text") if msgs else None) or r.text
        print(f"⚠️  Vonage SMS FAILED: {err}")
        if "Bad Credentials" in str(err):
            print("   → Kolla VONAGE_API_KEY och VONAGE_API_SECRET i Railway Variables. Kopiera exakt från Vonage Dashboard.")
        elif "invalid" in str(err).lower() or "from" in str(err).lower():
            print("   → VONAGE_FROM_NUMBER måste vara ett nummer du äger i Vonage (t.ex. virtuellt nummer). Format: +46701234567")
        return False
    except Exception as e:
        print(f"⚠️  Vonage SMS error: {e}")
        return False

def _get_customer_phone_from_webhook(body: dict) -> Optional[str]:
    """Hämta kundens telefonnummer från Vapi webhook-payload.
    Söker i: message.call.customer.number, body.phoneNumber, call.customer.number, m.fl."""
    msg = body.get("message") or {}
    call = msg.get("call") or body.get("call") or {}
    customer = call.get("customer") or msg.get("customer") or body.get("customer") or {}
    phone = (
        customer.get("number") or customer.get("phone") or customer.get("phoneNumber")
        or call.get("customerNumber") or call.get("phoneNumber") or call.get("from") or call.get("to")
        or msg.get("customerNumber") or msg.get("phoneNumber")
        or body.get("phoneNumber") or body.get("customerNumber")
    )
    if phone:
        phone = str(phone).strip()
    print(f"DEBUG SMS: phone sökväg -> found={phone}")
    return phone


def _get_restaurant_id_from_webhook(body: dict) -> str:
    """Legacy: returnerar bara restaurant_id. Använd _get_restaurant_from_webhook för multi-tenant."""
    rid, _ = _get_restaurant_from_webhook(body, None)
    return rid


# Cache: call_id -> (restaurant_id, restaurant_uuid) så att place_order vet vilken restaurang även om anropet saknar query-params.
# TTL 1 timme; rensa vid skriv om cache blir för stor. Dict/Tuple för Python 3.7/3.8-kompatibilitet.
_CALL_RESTAURANT_CACHE: Dict[str, dict] = {}
_CALL_CACHE_TTL_SEC = 3600
_CALL_CACHE_MAX_SIZE = 2000

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
            r = _supabase_client.table("restaurants").select("id, external_id").eq("external_id", rest_id).limit(1).execute()
            if r.data and len(r.data) > 0:
                row = r.data[0]
                return (row["external_id"], str(row["id"]))
        except Exception as e:
            print(f"⚠️  Restaurant lookup failed for rest_id={rest_id}: {e}")
    return (rest_id, RESTAURANT_UUID)


def _refresh_active_tenant_set() -> None:
    """Uppdatera _ACTIVE_TENANT_UUIDS från DB. Anropas lazy vid behov.
    Fas 3: när deleted_at finns, använd .is_("deleted_at", "null") eller filter för aktiva."""
    global _ACTIVE_TENANT_LAST_REFRESH, _ACTIVE_TENANT_UUIDS
    now = time.time()
    if now - _ACTIVE_TENANT_LAST_REFRESH < _ACTIVE_TENANT_REFRESH_INTERVAL_SEC:
        return
    _ACTIVE_TENANT_LAST_REFRESH = now
    if not _supabase_client:
        return
    try:
        r = _supabase_client.table("restaurants").select("id").execute()
        if r.data:
            _ACTIVE_TENANT_UUIDS = {str(row["id"]) for row in r.data}
        else:
            _ACTIVE_TENANT_UUIDS = set()
    except Exception as e:
        print(f"⚠️  Active tenant refresh failed: {e}")


def _is_tenant_active(restaurant_uuid: Optional[str]) -> bool:
    """Returnera True om restaurant_uuid finns i aktiva-tenant-set. Uppdaterar set om det är för gammalt."""
    if not restaurant_uuid:
        return False
    _refresh_active_tenant_set()
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
        ).eq("external_id", rest_id).limit(1).execute()
    except Exception:
        try:
            r = _supabase_client.table("restaurants").select("id, external_id").eq("external_id", rest_id).limit(1).execute()
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
    """Skicka notis när circuit breaker öppnas (Pushover)."""
    if not PUSHOVER_ALERTS_USER_KEY or not PUSHOVER_ALERTS_TOKEN:
        print("⚠️  Circuit breaker öppnad för rest_id=%s men PUSHOVER_ALERTS_* ej satt" % rest_id)
        return
    try:
        requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "user": PUSHOVER_ALERTS_USER_KEY,
                "token": PUSHOVER_ALERTS_TOKEN,
                "message": "[ALERT] Circuit breaker ÖPPNAD för rest_id=%s – %d fel på %d s. Kontrollera konfiguration."
                % (rest_id, _CIRCUIT_FAIL_THRESHOLD, _CIRCUIT_WINDOW_SEC),
                "title": "SwedenVoice Circuit Breaker",
            },
            timeout=5,
        )
    except Exception as e:
        print("⚠️  Circuit breaker alert failed: %s" % e)


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
    """Rensa config-cache och call_id-cache för denna tenant (Instant Kill). Tar omedelbart bort UUID från aktiva-set."""
    uuid_to_remove = None
    if rest_id in _CONFIG_CACHE:
        uuid_to_remove = _CONFIG_CACHE[rest_id].get("restaurant_uuid")
        del _CONFIG_CACHE[rest_id]
    to_del = [cid for cid, v in _CALL_RESTAURANT_CACHE.items() if v.get("restaurant_id") == rest_id]
    for cid in to_del:
        del _CALL_RESTAURANT_CACHE[cid]
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
            "dashboard": "/dashboard"
        }
    }

@app.get("/menu")
async def get_menu():
    """Get full menu"""
    menu = load_menu()
    return JSONResponse(content=menu)

@app.get("/orders")
async def get_orders():
    """Get all orders"""
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


def _process_place_order(items: List[OrderItem], special_requests: Optional[str] = None, customer_phone: Optional[str] = None, skip_pushover: bool = False) -> Order:
    """Process order: validate, save, print, send Pushover (om inte skip_pushover).
    customer_phone inkluderas i Pushover när angiven. Callers med body kan anropa send_pushover själva efteråt med telefon."""
    enriched_items = []
    per_item_specs = []
    for item in items:
        menu_item = find_menu_item(item.id)
        if not menu_item:
            raise HTTPException(
                status_code=404, 
                detail=f"Menu item with ID {item.id} not found"
            )
        name = menu_item['name']
        enriched_items.append(OrderItem(
            id=item.id,
            name=name,
            quantity=item.quantity,
            price=menu_item['price'],
            special_requests=item.special_requests
        ))
        if item.special_requests and item.special_requests.strip():
            per_item_specs.append(f"{item.quantity}x {name}: {item.special_requests.strip()}")
    combined_special = "; ".join(per_item_specs) if per_item_specs else special_requests
    total_price = calculate_total_price(enriched_items)
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
    if not skip_pushover:
        send_pushover_notification(order, customer_phone=customer_phone)
    return order


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
                customer_phone = _get_customer_phone_from_webhook(body)
                calls = _extract_vapi_tool_calls(msg)
                results = []
                for tool_call_id, params in calls:
                    items_data = _parse_items_from_params(params)
                    if not items_data:
                        results.append({
                            "name": "place_order",
                            "toolCallId": tool_call_id,
                            "result": json.dumps({"success": False, "error": "No items in order"})
                        })
                        continue
                    try:
                        items = [OrderItem(**it) for it in items_data]
                        order = _process_place_order(items, params.get("special_requests"), skip_pushover=True)
                        send_pushover_notification(order, customer_phone=customer_phone)
                        customer_name = params.get("customer_name") or params.get("customerName") or ""
                        _insert_order_to_supabase(order, restaurant_id, customer_name=customer_name, customer_phone=customer_phone, restaurant_uuid=restaurant_uuid)
                        _circuit_breaker_record_success(rest_id)
                        results.append({
                            "name": "place_order",
                            "toolCallId": tool_call_id,
                            "result": json.dumps({
                                "success": True,
                                "order_id": order.order_id,
                                "total_price": order.total_price
                            })
                        })
                        try:
                            print("=== SMS CHECKPOINT A (i /place_order) ===")
                            print(f"DEBUG SMS [/place_order]: Sending SMS to: {customer_phone}")
                            if customer_phone:
                                print("=== SMS CHECKPOINT B (innan Vonage i /place_order) ===")
                                sms_result = send_sms_order_confirmation(order, customer_phone)
                                print(f"=== SMS CHECKPOINT C: Vonage result={sms_result} ===")
                            else:
                                print("DEBUG SMS [/place_order]: Ingen kundtelefon – SMS ej skickat")
                        except Exception as sms_err:
                            print(f"⚠️  SMS-orderbekräftelse misslyckades: {sms_err}")
                    except Exception as e:
                        if _circuit_breaker_record_failure(rest_id):
                            _send_circuit_breaker_alert(rest_id)
                        results.append({
                            "name": "place_order",
                            "toolCallId": tool_call_id,
                            "result": json.dumps({"success": False, "error": str(e)})
                        })
                if results:
                    print(f"✅ Vapi tool-call processed, {len(results)} result(s)")
                    return JSONResponse(content={"results": results})
                print("⚠️  Body hade message/toolCalls men INGEN place_order hittades – kolla format!")
                raise HTTPException(status_code=400, detail="No place_order tool call found")
        
        # Direct format: {"items": [...], "special_requests": "..."}
        req = PlaceOrderRequest(**body)
        order = _process_place_order(req.items, req.special_requests)
        return JSONResponse(content={
            "success": True,
            "message": "Order placed successfully",
            "order": order.model_dump()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error placing order: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update_order_status")
async def update_order_status(request: UpdateOrderStatusRequest):
    """Update order status (e.g., pending -> ready -> completed)"""
    try:
        orders = load_orders()
        
        # Find and update order
        order_found = False
        for order in orders:
            if order['order_id'] == request.order_id:
                order['status'] = request.status
                order_found = True
                print(f"✅ Order {request.order_id} updated to status: {request.status}")
                break
        
        if not order_found:
            raise HTTPException(status_code=404, detail="Order not found")
        
        save_orders(orders)
        
        return JSONResponse(content={
            "success": True,
            "message": f"Order status updated to {request.status}"
        })
        
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
            "groq_configured": bool(GROQ_API_KEY),
            "pushover_configured": bool(PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN)
        }
    })

@app.get("/test_pushover")
async def test_pushover():
    """Test Pushover – skickar en testnotis för att verifiera konfiguration"""
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        return JSONResponse(content={
            "success": False,
            "error": "Pushover not configured (missing PUSHOVER_USER_KEY or PUSHOVER_API_TOKEN in .env)"
        }, status_code=400)
    try:
        r = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": PUSHOVER_API_TOKEN,
                "user": PUSHOVER_USER_KEY,
                "title": "Gislegrillen – Test",
                "message": "Om du ser detta fungerar Pushover!",
                "priority": 0
            },
            timeout=10
        )
        if r.status_code == 200:
            return {"success": True, "message": "Testnotis skickad – kolla mobilen!"}
        err = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return JSONResponse(
            content={"success": False, "error": r.text, "pushover_errors": err.get("errors", [])},
            status_code=400
        )
    except Exception as e:
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)

# ==================== FAS 1: ADMIN (Instant Kill) ====================

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

        # Handle end-of-call-report
        # OBS: Vi skippar order-skapande här för att undvika DUBBLA Pushover/ordrar.
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
            customer_phone = _get_customer_phone_from_webhook(body)
            calls = _extract_vapi_tool_calls(msg)
            results = []
            for tool_call_id, params in calls:
                items_data = _parse_items_from_params(params)
                if not items_data:
                    results.append({
                        "name": "place_order",
                        "toolCallId": tool_call_id,
                        "result": json.dumps({"success": False, "error": "No items"})
                    })
                    continue
                try:
                    items = [OrderItem(**it) for it in items_data]
                    order = _process_place_order(items, params.get("special_requests"), skip_pushover=True)
                    send_pushover_notification(order, customer_phone=customer_phone)
                    customer_name = params.get("customer_name") or params.get("customerName") or ""
                    _insert_order_to_supabase(order, restaurant_id, customer_name=customer_name, customer_phone=customer_phone, restaurant_uuid=restaurant_uuid)
                    _circuit_breaker_record_success(rest_id)
                    results.append({
                        "name": "place_order",
                        "toolCallId": tool_call_id,
                        "result": json.dumps({"success": True, "order_id": order.order_id})
                    })
                    print(f"✅ Processed place_order via webhook: {order.order_id} (restaurant_id={restaurant_id}, restaurant_uuid={restaurant_uuid})")
                    print("=== SMS CHECKPOINT 1 ===")
                    try:
                        print("=== SMS CHECKPOINT 2 ===")
                        print(f"DEBUG SMS: Sending SMS to: {customer_phone}")
                        if customer_phone:
                            print("=== SMS CHECKPOINT 3 (innan Vonage-anrop) ===")
                            sms_result = send_sms_order_confirmation(order, customer_phone)
                            print(f"=== SMS CHECKPOINT 4 (efter Vonage): result={sms_result} ===")
                        else:
                            print("⚠️  Ingen kundtelefon i webhook – SMS ej skickat")
                            print("   → Vapi skickar kanske inte caller-nummer i tool-calls. Kolla DEBUG SMS-raden ovan för payload-struktur.")
                    except Exception as sms_err:
                        print(f"⚠️  SMS-orderbekräftelse misslyckades (påverkar inte order): {sms_err}")
                except Exception as e:
                    print(f"❌ place_order error in webhook: {e}")
                    if _circuit_breaker_record_failure(rest_id):
                        _send_circuit_breaker_alert(rest_id)
                    results.append({
                        "name": "place_order",
                        "toolCallId": tool_call_id,
                        "result": json.dumps({"success": False, "error": str(e)})
                    })
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
    if not GROQ_API_KEY:
        print("⚠️  WARNING: GROQ_API_KEY not configured!")
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        print("⚠️  WARNING: Pushover credentials not configured!")
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
