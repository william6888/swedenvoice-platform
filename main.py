"""
Gislegrillen Voice AI Order System
FastAPI backend for Vapi.ai integration with Groq LLM
"""

import json
import os
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

# ==================== DATA MODELS ====================

class OrderItem(BaseModel):
    id: int
    name: str
    quantity: int
    price: Optional[float] = None

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
    """Generate unique order ID"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"ORD-{timestamp}"

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
    
    try:
        message = f"🔔 Ny beställning!\n\n"
        message += f"Order: {order.order_id}\n"
        message += f"Tid: {order.timestamp}\n\n"
        
        for item in order.items:
            message += f"• {item.quantity}x {item.name}\n"
        
        if order.special_requests:
            message += f"\n⚠️ Special: {order.special_requests}\n"
        
        message += f"\nTotalt: {order.total_price} kr"
        
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
        else:
            print(f"⚠️  Pushover notification failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error sending Pushover notification: {e}")
        return False

# ==================== API ENDPOINTS ====================

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

@app.post("/place_order")
async def place_order(request: PlaceOrderRequest):
    """
    Main order placement endpoint - Called by Vapi tool
    
    This function:
    1. Validates and calculates prices
    2. Saves order to orders.json
    3. Prints kitchen ticket to console
    4. Sends Pushover notification
    """
    try:
        # Enrich items with prices from menu
        enriched_items = []
        for item in request.items:
            menu_item = find_menu_item(item.id)
            if not menu_item:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Menu item with ID {item.id} not found"
                )
            
            enriched_items.append(OrderItem(
                id=item.id,
                name=item.name,
                quantity=item.quantity,
                price=menu_item['price']
            ))
        
        # Calculate total
        total_price = calculate_total_price(enriched_items)
        
        # Generate order
        order = Order(
            order_id=generate_order_id(),
            items=enriched_items,
            special_requests=request.special_requests,
            total_price=total_price,
            status="pending",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        # Save to orders.json
        orders = load_orders()
        orders.append(order.model_dump())
        save_orders(orders)
        
        # Print kitchen ticket
        print_kitchen_ticket(order)
        
        # Send Pushover notification
        send_pushover_notification(order)
        
        return JSONResponse(content={
            "success": True,
            "message": "Order placed successfully",
            "order": order.model_dump()
        })
        
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

# ==================== VAPI WEBHOOK ENDPOINTS ====================

@app.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    """
    Vapi webhook endpoint for call events
    Handles: call started, ended, tool calls, etc.
    """
    try:
        body = await request.json()
        event_type = body.get("message", {}).get("type", "unknown")
        
        print(f"📞 Vapi Webhook Event: {event_type}")
        print(f"   Data: {json.dumps(body, indent=2)}")
        
        return JSONResponse(content={
            "success": True,
            "event": event_type
        })
        
    except Exception as e:
        print(f"❌ Vapi webhook error: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        }, status_code=500)

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
    
    print("\n✅ Server ready to accept orders!\n")
    
    # Run server
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info"
    )
