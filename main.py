"""
Gislegrillen Voice AI Order System
FastAPI backend for Vapi.ai integration with Groq LLM
"""

import json
import os
import time
from datetime import datetime
from typing import List, Optional
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn

# Load environment variables
load_dotenv()

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

@app.on_event("startup")
async def startup_debug():
    """DEBUG: Logga Vonage env vid app-start (körs också på Railway)."""
    print(f"DEBUG VONAGE: VONAGE_API_KEY={'SET' if VONAGE_API_KEY else 'MISSING'}")
    print(f"DEBUG VONAGE: VONAGE_API_SECRET={'SET' if VONAGE_API_SECRET else 'MISSING'}")
    print(f"DEBUG VONAGE: VONAGE_FROM_NUMBER={'SET' if VONAGE_FROM_NUMBER else 'MISSING'}")

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

# ==================== HELPER FUNCTIONS ====================

def _parse_items_from_params(params: dict) -> list:
    """Extrahera items från params – stödjer items, order.items, full_order.items."""
    items = params.get("items", [])
    if not items and "order" in params:
        items = params.get("order", {}).get("items", [])
    if not items and "full_order" in params:
        items = params.get("full_order", {}).get("items", [])
    if not isinstance(items, list):
        return []
    # Unwrap { "item": {...} } och normalisera special_requests (snake_case + camelCase)
    out = []
    for it in items:
        if isinstance(it, dict) and "item" in it and isinstance(it.get("item"), dict):
            d = dict(it["item"])
        elif isinstance(it, dict):
            d = dict(it)
        else:
            continue
        if "specialRequests" in d and "special_requests" not in d:
            d["special_requests"] = d.pop("specialRequests")
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

def send_pushover_notification(order: Order):
    """Send push notification via Pushover API"""
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        print("⚠️  Pushover credentials not configured. Skipping notification.")
        return False

    print(f"📤 Skickar Pushover-notis för order {order.order_id}...")
    message = f"🔔 Ny beställning!\n\n"
    message += f"Order: {order.order_id}\n"
    message += f"Tid: {order.timestamp}\n\n"
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

def _format_order_sms(order: Order) -> str:
    """Formatera beställning till SMS-text enligt spec."""
    lines = ["Hej! Detta är din orderbekräftelse från Gisslegrillen 🍕", ""]
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
        return False
    except Exception as e:
        print(f"⚠️  Vonage SMS error: {e}")
        return False

def _get_customer_phone_from_webhook(body: dict) -> Optional[str]:
    """Hämta kundens telefonnummer från Vapi webhook-payload."""
    msg = body.get("message") or {}
    call = msg.get("call") or {}
    customer = call.get("customer") or msg.get("customer") or {}
    # Sökvägar: message.call.customer.number (primär), customer.phone, customer.phoneNumber
    phone = customer.get("number") or customer.get("phone") or customer.get("phoneNumber")
    print(f"DEBUG SMS: phone sökväg = message.call.customer.number|phone|phoneNumber -> found={phone}")
    return phone

# ==================== API ENDPOINTS ====================

@app.get("/debug-vonage")
async def debug_vonage():
    """DEBUG: Kontrollera om Vonage env-variabler är satta (visar inte värden)."""
    return {
        "VONAGE_API_KEY": "SET" if VONAGE_API_KEY else "MISSING",
        "VONAGE_API_SECRET": "SET" if VONAGE_API_SECRET else "MISSING",
        "VONAGE_FROM_NUMBER": "SET" if VONAGE_FROM_NUMBER else "MISSING",
    }

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
        if name != "place_order":
            return
        args = fn.get("arguments") or fn.get("parameters") or tc.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
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


def _process_place_order(items: List[OrderItem], special_requests: Optional[str] = None) -> Order:
    """Process order: validate, save, print, send Pushover. Returns Order."""
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
    send_pushover_notification(order)
    return order


@app.post("/place_order")
async def place_order(request: Request):
    """
    Main order placement endpoint - Called by Vapi tool OR direct API.
    Supports both Vapi tool-calls format and direct JSON format.
    """
    try:
        body = await request.json()
        print("\n" + "="*50)
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
                        order = _process_place_order(items, params.get("special_requests"))
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
                            customer_phone = _get_customer_phone_from_webhook(body)
                            print(f"DEBUG SMS [/place_order]: Sending SMS to: {customer_phone}")
                            if customer_phone:
                                sms_result = send_sms_order_confirmation(order, customer_phone)
                                print(f"DEBUG SMS [/place_order]: SMS result: {sms_result}")
                            else:
                                print("DEBUG SMS [/place_order]: Ingen kundtelefon – SMS ej skickat")
                        except Exception as sms_err:
                            print(f"⚠️  SMS-orderbekräftelse misslyckades: {sms_err}")
                    except Exception as e:
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

# ==================== VAPI WEBHOOK ENDPOINTS ====================

@app.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    """
    Vapi webhook endpoint for call events.
    Handles: call started, ended, tool-calls, etc.
    If tool-calls arrive here (assistant-level URL), process place_order.
    """
    try:
        body = await request.json()
        print(f"FULL BODY KEYS: {json.dumps(list(body.keys()))}")
        print(f"MESSAGE TYPE: {body.get('message') and body['message'].get('type')}")

        msg = body.get("message", {})
        event_type = msg.get("type", "unknown")

        print("\n" + "-"*50)
        print(f"📞 VAPI WEBHOOK: event_type={event_type}")
        if event_type != "tool-calls":
            print(f"   (Ignorerar – väntar på tool-calls för place_order)")
        
        # Handle tool-calls (stödjer toolCallList och toolWithToolCallList)
        if event_type == "tool-calls":
            # DEBUG: logga message.call struktur för att verifiera kundnummer-sökväg
            msg_struct = body.get("message") or {}
            call_data = msg_struct.get("call") or {}
            cust_data = call_data.get("customer") or msg_struct.get("customer") or {}
            print(f"DEBUG SMS: message.call keys={list(call_data.keys())}, customer keys={list(cust_data.keys())}")
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
                    order = _process_place_order(items, params.get("special_requests"))
                    results.append({
                        "name": "place_order",
                        "toolCallId": tool_call_id,
                        "result": json.dumps({"success": True, "order_id": order.order_id})
                    })
                    print(f"✅ Processed place_order via webhook: {order.order_id}")
                    # Skicka SMS-orderbekräftelse – blockar inte svaret till Vapi
                    print("DEBUG SMS: Når SMS-kod – försöker hämta customer_phone")
                    try:
                        customer_phone = _get_customer_phone_from_webhook(body)
                        print(f"DEBUG SMS: Sending SMS to: {customer_phone}")
                        if customer_phone:
                            sms_result = send_sms_order_confirmation(order, customer_phone)
                            print(f"DEBUG SMS: SMS result: {sms_result}")
                        else:
                            print("⚠️  Ingen kundtelefon i webhook – SMS ej skickat")
                    except Exception as sms_err:
                        print(f"⚠️  SMS-orderbekräftelse misslyckades (påverkar inte order): {sms_err}")
                except Exception as e:
                    print(f"❌ place_order error in webhook: {e}")
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
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)

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
