# Quick Start Guide - Gislegrillen Voice AI Order System

Get up and running in 5 minutes!

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Git

## Installation

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/william6888/Gislegrillen_
cd Gislegrillen_

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
# Copy template
cp .env.template .env

# Edit .env with your favorite editor
nano .env  # or vim, code, etc.
```

Add your API keys:
```env
VAPI_API_KEY=your_vapi_api_key_here
GROQ_API_KEY=your_groq_api_key_here
PUSHOVER_USER_KEY=your_pushover_user_key_here
PUSHOVER_API_TOKEN=your_pushover_api_token_here
```

**Get API Keys:**
- Vapi: https://vapi.ai → Dashboard → API Keys
- Groq: https://console.groq.com → API Keys
- Pushover: https://pushover.net → Create Application

### 3. Run the Server

```bash
python main.py
```

You should see:
```
============================================================
         🍕 GISLEGRILLEN VOICE AI ORDER SYSTEM 🍕
============================================================
FastAPI Server Starting...
Host: 0.0.0.0
Port: 8000
Dashboard: http://localhost:8000/dashboard
============================================================

✅ Server ready to accept orders!
```

### 4. Test Locally

Open your browser:
- **Dashboard:** http://localhost:8000/dashboard
- **API Docs:** http://localhost:8000/docs
- **Menu:** http://localhost:8000/menu

### 5. Expose to Internet (for Vapi)

```bash
# Deploy to Railway - see RAILWAY_GUIDE.md
```

Copy your Railway URL (e.g., `https://gislegrillen-production.up.railway.app`)

### 6. Configure Vapi

Follow the detailed steps in `VAPI_SETUP_GUIDE.md`

**Quick version:**
1. Create Assistant in Vapi
2. Set Model: Groq → llama-3.1-70b-versatile
3. Copy `system_prompt.md` content to System Prompt
4. Set Server URL: your Railway URL + `/vapi/webhook`
5. Buy/assign phone number
6. Test!

## Test the System

### Manual API Test

```bash
curl -X POST http://localhost:8000/place_order \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"id": 4, "name": "Hawaii", "quantity": 1},
      {"id": 401, "name": "Coca-Cola 33cl", "quantity": 1}
    ],
    "special_requests": "Ingen lök"
  }'
```

You should see:
- Kitchen ticket printed in console
- Order saved to `orders.json`
- Order visible on dashboard
- Pushover notification (if configured)

### Run Test Suite

```bash
python test_system.py
```

All tests should pass ✅

## Project Structure

```
gislegrillen-order-system/
├── main.py              # FastAPI server (run this!)
├── menu.json            # Menu database (52 pizzas + more)
├── orders.json          # Order storage (auto-created)
├── system_prompt.md     # AI personality (copy to Vapi)
├── index.html           # Kitchen dashboard
├── requirements.txt     # Dependencies
├── .env                 # Your API keys (create from template)
├── .env.template        # Template for API keys
├── test_system.py       # Test suite
└── README.md            # Full documentation
```

## Common Commands

```bash
# Run server
python main.py

# Run tests
python test_system.py

# Check menu
curl http://localhost:8000/menu | python -m json.tool

# Check orders
curl http://localhost:8000/orders | python -m json.tool

# Check health
curl http://localhost:8000/health | python -m json.tool
```

## Usage Flow

1. **Customer calls** → Vapi phone number
2. **AI greets** → "Hej, Gislegrillen! Vad får det lov att vara?"
3. **Customer orders** → "En Hawaii och en Kebabpizza"
4. **AI confirms** → Repeats order
5. **AI places order** → Calls your `/place_order` endpoint
6. **You get notified** → Pushover notification + Console ticket
7. **You prepare food** → Check dashboard
8. **You mark ready** → Click button on dashboard
9. **Customer picks up** → Happy customer! 🍕

## Troubleshooting

### Server won't start
```bash
# Check if port 8000 is in use
lsof -i :8000

# Try different port
PORT=8080 python main.py
```

### API keys not working
```bash
# Verify .env file exists
ls -la .env

# Check if keys are loaded
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('VAPI_API_KEY:', bool(os.getenv('VAPI_API_KEY')))"
```

### Orders not appearing
```bash
# Check orders.json permissions
ls -la orders.json

# Should be writable by current user
chmod 644 orders.json
```

## Next Steps

1. ✅ Server running locally
2. ✅ Dashboard accessible
3. ✅ API keys configured
4. 📱 Configure Vapi assistant (see VAPI_SETUP_GUIDE.md)
5. 📞 Test with phone call
6. 🚀 Deploy to production server (optional)

## Production Deployment

### Quick Deploy Options

**Heroku:**
```bash
# Add Procfile
echo "web: python main.py" > Procfile
git push heroku main
```

**DigitalOcean App Platform:**
- Connect GitHub repo
- Set environment variables
- Deploy automatically

**AWS EC2:**
- Launch Ubuntu instance
- Install Python
- Clone repo
- Run with systemd service

See README.md for detailed deployment instructions.

## Support

- 📖 Full docs: `README.md`
- 🔧 Vapi setup: `VAPI_SETUP_GUIDE.md`
- 🧪 Run tests: `python test_system.py`
- 📊 Dashboard: http://localhost:8000/dashboard
- 📚 API docs: http://localhost:8000/docs

## What Makes This System Special?

✨ **Plug-and-Play:** Just add API keys and run
✨ **Swedish Native:** Professional Swedish AI personality
✨ **Complete Menu:** 52 pizzas + kebabs, burgers, sides
✨ **Real-time Dashboard:** Beautiful Bootstrap UI
✨ **Instant Notifications:** Pushover integration
✨ **Production Ready:** Error handling, logging, persistence
✨ **Open Source:** Customize as you need

---

**Ready to take orders!** 🍕📞

Questions? Check the full README.md or test with:
```bash
python test_system.py
```

Happy ordering! 🎉
