# 🍕 Gislegrillen Voice AI Order System

A production-ready, plug-and-play Voice AI ordering system for Gislegrillen pizzeria. Built with Vapi.ai for voice handling, Groq (Llama 3) as the AI brain, and FastAPI for robust backend logic.

## 🎯 Features

- **Voice AI Integration**: Seamless integration with Vapi.ai for natural phone conversations
- **Swedish AI Personality**: Professional Swedish-speaking AI with local pizzeria authenticity
- **Smart Order Processing**: Automatic price calculation, validation, and persistence
- **Kitchen Dashboard**: Real-time web dashboard for managing orders
- **Push Notifications**: Instant order alerts via Pushover
- **Production Ready**: Comprehensive error handling, logging, and monitoring

## 📁 Project Structure

```
gislegrillen-order-system/
├── main.py                 # FastAPI server with all endpoints
├── menu.json              # Complete menu database (pizzas 1-52, kebabs, burgers, sides)
├── orders.json            # Persistent order storage
├── system_prompt.md       # Swedish AI personality instructions
├── index.html             # Kitchen dashboard (Bootstrap)
├── requirements.txt       # Python dependencies
├── .env.template          # Environment variables template
├── .gitignore            # Git ignore rules
└── README.md             # This file
```

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.8+
- Vapi.ai account (https://vapi.ai)
- Groq API key (https://console.groq.com)
- Pushover account (optional, https://pushover.net)

### 2. Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd gislegrillen-order-system

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.template .env
# Edit .env with your actual API keys
```

### 3. Configuration

Edit `.env` file with your credentials:

```env
VAPI_API_KEY=your_vapi_api_key_here
GROQ_API_KEY=your_groq_api_key_here
PUSHOVER_USER_KEY=your_pushover_user_key_here
PUSHOVER_API_TOKEN=your_pushover_api_token_here
HOST=0.0.0.0
PORT=8000
```

### 4. Run the Server

```bash
python main.py
```

The server will start on `http://localhost:8000`

## 📱 Vapi.ai Setup

### Create Assistant

1. Go to Vapi.ai dashboard
2. Create a new assistant with these settings:

**Model Configuration:**
- Provider: Groq
- Model: llama-3.1-70b-versatile
- Temperature: 0.7
- Max Tokens: 500

**System Prompt:**
Copy the contents from `system_prompt.md`

**Voice Settings:**
- Provider: ElevenLabs or similar
- Language: Swedish (sv-SE)
- Voice: Choose a professional, friendly voice

### Configure Tool (Function Calling)

Add a server tool:

**Tool Name:** `place_order`

**Server URL:** `https://your-domain.com/place_order` (or use ngrok for testing)

**Description:** "Place a customer order with items, quantities, and special requests"

**Parameters Schema:**
```json
{
  "type": "object",
  "properties": {
    "items": {
      "type": "array",
      "description": "List of ordered items",
      "items": {
        "type": "object",
        "properties": {
          "id": {"type": "integer", "description": "Menu item ID"},
          "name": {"type": "string", "description": "Menu item name"},
          "quantity": {"type": "integer", "description": "Quantity ordered"}
        },
        "required": ["id", "name", "quantity"]
      }
    },
    "special_requests": {
      "type": "string",
      "description": "Special requests like 'ingen lök', 'extra ost'"
    }
  },
  "required": ["items"]
}
```

## 🎨 Kitchen Dashboard

Access the dashboard at: `http://localhost:8000/dashboard`

**Features:**
- Real-time order display
- Order status management (Pending → Ready → Completed)
- Special requests highlighting
- Auto-refresh every 30 seconds
- Beautiful Bootstrap UI

## 📡 API Endpoints

### Core Endpoints

- `GET /` - API information
- `GET /menu` - Get full menu
- `GET /orders` - Get all orders
- `POST /place_order` - Place new order (called by Vapi)
- `POST /update_order_status` - Update order status
- `GET /dashboard` - Kitchen dashboard
- `GET /system_prompt` - Get system prompt
- `GET /health` - Health check

### Webhooks

- `POST /vapi/webhook` - Vapi webhook events

## 🔔 Order Flow

1. **Customer calls** → Vapi answers with Swedish AI personality
2. **AI takes order** → Validates items from menu.json
3. **AI confirms** → Customer approves order
4. **AI calls tool** → `place_order` endpoint triggered
5. **Backend processes:**
   - Calculates total price
   - Saves to orders.json
   - Prints kitchen ticket to console
   - Sends Pushover notification
6. **AI confirms** → "Tack för din beställning! Den är klar om 15 minuter."
7. **Kitchen staff** → Views order on dashboard, marks as ready

## 📝 Example Order

**Console Output (Kitchen Ticket):**
```
============================================================
                    🔔 KÖKS-BONG! 🔔                        
============================================================
ORDER ID: ORD-20260208153045
TID: 2026-02-08 15:30:45
------------------------------------------------------------
ARTIKLAR:
  [1x] Hawaii (98 kr)
  [1x] Kebabpizza (110 kr)
  [1x] Coca-Cola 33cl (25 kr)
------------------------------------------------------------
⚠️  SPECIAL: Kebabpizza utan lök
------------------------------------------------------------
TOTALT: 233 kr
============================================================
STATUS: PENDING
============================================================
```

## 🛠️ Development

### Testing Locally

Use ngrok to expose your local server:

```bash
ngrok http 8000
```

Use the ngrok URL in Vapi tool configuration.

### Adding Menu Items

Edit `menu.json` and add items to the appropriate category:

```json
{
  "id": 53,
  "name": "New Pizza",
  "price": 120,
  "description": "Tomatsås, ost, toppings"
}
```

### Customizing AI Personality

Edit `system_prompt.md` to change the AI's behavior, tone, or conversation flow.

## 🔒 Security Notes

- Never commit `.env` file to git
- Use HTTPS in production
- Validate all incoming requests
- Implement rate limiting for production use
- Store sensitive data securely

## 📊 Monitoring

The system logs important events to console:
- Order placement
- Kitchen tickets
- Pushover notifications
- API errors
- Configuration warnings

## 🐛 Troubleshooting

**Server won't start:**
- Check Python version (3.8+)
- Verify all dependencies installed
- Check port 8000 is available

**Orders not appearing:**
- Check `orders.json` permissions
- Verify API endpoint is accessible
- Check browser console for errors

**Pushover not working:**
- Verify API keys in `.env`
- Check Pushover account status
- Look for error messages in console

**Vapi tool not working:**
- Verify server URL is correct and accessible
- Check tool schema matches endpoint
- Enable Vapi debug logs

## 📄 License

MIT License - feel free to use for your own projects

## 🙏 Support

For issues or questions:
1. Check the troubleshooting section
2. Review server logs
3. Verify Vapi configuration
4. Check API endpoint accessibility

## 🚀 Deployment

For production deployment:
1. Use a proper WSGI server (Gunicorn)
2. Set up HTTPS with SSL certificates
3. Use a proper database (PostgreSQL)
4. Implement authentication for dashboard
5. Set up monitoring (Sentry, etc.)
6. Use environment-specific configuration

---

**Built with ❤️ for Gislegrillen**

*Plug-and-Play Voice AI Ordering Made Simple*
