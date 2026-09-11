# 🍕 Gislegrillen Voice AI Order System

A production-ready, plug-and-play Voice AI ordering system for Gislegrillen pizzeria. Built with Vapi.ai for voice handling, FastAPI for backend logic, optional Vonage SMS and Supabase.

## 🎯 Features

- **Voice AI Integration**: Seamless integration with Vapi.ai for natural phone conversations
- **Swedish AI Personality**: Professional Swedish-speaking AI with local pizzeria authenticity
- **Smart Order Processing**: Menu validation, tenant isolation and persistence without prices
- **Kitchen Dashboard**: Real-time web dashboard for managing orders
- **Kitchen visibility**: Dashboard, Supabase/Lovable, and console/Railway logs for kitchen tickets
- **Production Ready**: Comprehensive error handling, logging, and monitoring

## 📁 Project Structure

```
gislegrillen-order-system/
├── main.py                 # FastAPI server with all endpoints
├── menu.json              # Complete menu database (pizzas 1-52, kebabs, burgers, sides)
├── backup_core.py         # Strict encrypted Supabase backup + verification
├── system_prompt.md       # Swedish AI personality instructions
├── index.html             # Kitchen dashboard (Bootstrap)
├── requirements.txt       # Python dependencies
├── requirements-backup.txt # Pinned GitHub backup dependencies
├── .env.template          # Environment variables template
├── .gitignore            # Git ignore rules
└── README.md             # This file
```

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.11
- Vapi.ai account (https://vapi.ai)
- Optional: Vonage for SMS, Supabase for cloud orders (see `.env.template`)

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
HOST=0.0.0.0
PORT=8000
# See .env.template for Vonage, Supabase, ADMIN_SECRET, etc.
```

### 4. Run the Server

```bash
python main.py
```

The server will start on `http://localhost:8000`

## 📱 Vapi.ai Setup

Use `VAPI_PRODUCTION_CONFIG.md` as the only production setup reference. It
defines the tested model, Swedish transcriber, voice, strict synchronous
`draft_order` → readback → explicit confirmation → `place_order` flow, schemas
without menu IDs, and the Vapi confirmation rejection guard.

Use `scripts/onboard_pizzeria.py` to clone this configuration safely for a new
tenant. Do not recreate tools from older examples in `VAPI_SETUP_GUIDE.md`.

## 🎨 Kitchen Dashboard

Access the dashboard at: `http://localhost:8000/dashboard`

Dashboarden kräver inloggning. Ange `DASHBOARD_ACCESS_KEY` (eller
`ADMIN_SECRET` om separat dashboardnyckel inte är satt); servern skapar därefter
en tidsbegränsad HttpOnly-session. `/orders` och `/update_order_status` är inte
publika API:er.

**Features:**
- Real-time order display
- Order status management (Pending → Ready → Completed)
- Special requests highlighting
- Auto-refresh every 30 seconds
- Beautiful Bootstrap UI

## 📡 API Endpoints

### Core Endpoints

- `GET /` - API information
- `GET /menu` - Get full menu (cached 3 min; clear with `POST /admin/menu/invalidate` if you change menu.json)
- `GET /api/keywords` - Keywords/keyterms for speech recognition (sanitized, max 50 chars)
- `GET /orders` - Get tenant-scoped orders (dashboard authentication required)
- `POST /place_order` - Place new order (called by Vapi)
- `POST /update_order_status` - Update tenant-scoped order status (dashboard authentication required)
- `GET /dashboard` - Kitchen dashboard
- `GET /system_prompt` - Get system prompt
- `GET /health` - Health check

### Webhooks

- `POST /vapi/webhook` - Vapi webhook events (set Server URL in Vapi to `https://<your-railway-url>/vapi/webhook`)

### Keyword boosting (Vapi / Speechmatics)

- `GET /api/keywords` - Returns `keywords` (single words) and `keyterms` (product phrases) from the menu. Values are sanitized (letters, digits, spaces, hyphen, apostrophe, parentheses; Swedish åäö allowed) and truncated to 50 chars for provider compatibility. Use in Vapi or your speech-to-text provider (e.g. Speechmatics) to improve recognition. Optional query: `?rest_id=...` for future per-tenant menus.

### Admin (Fas 2: meny-cache)

- `POST /admin/menu/invalidate` - Clears the menu cache so the next `GET /menu` and `GET /api/keywords` reload from `menu.json`. Use after editing the menu so you don’t have to wait 3 minutes or restart. Requires header `X-Admin-Key: <ADMIN_SECRET>`. Optional query `?rest_id=...` to clear only that cache key.

**Varför en worker?** Procfile använder `--workers 1` så att meny-cache och tenant-invalidate gäller direkt i hela appen. Flera workers skulle ge var sin cache; då gäller invalidate bara för den process som fick anropet.

**Flera pizzerior:** Varje pizzeria har egen databasmeny och cache via
`rest_id`. En okänd tenant får aldrig Gislegrillens standardmeny. Se
**MULTI_PIZZERIA.md**.

## 🔔 Order Flow

1. **Customer calls** → Vapi answers with Swedish AI personality
2. **AI takes order** → Validates items from menu.json
3. **AI drafts** → Calls `draft_order` and reads the canonical result
4. **Customer confirms** → Explicitly approves the complete readback
5. **AI commits** → Calls synchronous `place_order` with the unchanged payload
6. **Backend processes:**
   - Validates items against the tenant's menu
   - Saves to Supabase (system of record)
   - Prints kitchen ticket to console / logs
   - Sends SMS (Vonage) when configured
7. **AI confirms** → Only after the tool returns `success: true`; never promises
   a preparation time
8. **Kitchen staff** → Views order on dashboard, marks as ready

Systemet hanterar medvetet **inga priser**. Betalning sker på plats.

## 🛠️ Development

### Testing Locally

Deploy to Railway (see RAILWAY_GUIDE.md) and use the Railway URL in Vapi.

### Adding Menu Items

Edit `menu.json` and add items to the appropriate category:

```json
{
  "id": 53,
  "name": "New Pizza",
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
- SMS / Supabase status (when used)
- API errors
- Configuration warnings

## 🐛 Troubleshooting

**Server won't start:**
- Check Python version (3.8+)
- Verify all dependencies installed
- Check port 8000 is available

**Orders not appearing:**
- Verify `/health`, Supabase and the `/orders` endpoint
- Check the Lovable/KDS connection and browser console

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
