# Vapi.ai Setup Guide for Gislegrillen

This guide will help you configure Vapi.ai to work with your Gislegrillen Voice AI Order System.

## Step 1: Expose Your Server

### Option A: Using ngrok (for testing)

```bash
# Install ngrok from https://ngrok.com
ngrok http 8000
```

You'll get a URL like: `https://abc123.ngrok.io`

### Option B: Production Deployment

Deploy to a server with a public domain and HTTPS (e.g., AWS, DigitalOcean, Heroku)

## Step 2: Create Vapi Assistant

1. Go to https://vapi.ai/dashboard
2. Click "Create Assistant"
3. Fill in the following:

### Basic Settings

**Name:** Gislegrillen Order Bot
**First Message:** "Hej, Gislegrillen! Vad får det lov att vara?"

### Model Configuration

- **Provider:** Groq
- **Model:** llama-3.1-70b-versatile
- **Temperature:** 0.7
- **Max Tokens:** 500

### System Prompt

Copy and paste the ENTIRE contents of `system_prompt.md` into the system prompt field.

### Voice Settings

- **Provider:** ElevenLabs (or Play.ht)
- **Language:** Swedish (sv-SE)
- **Voice ID:** Choose a professional, friendly Swedish voice
- **Speed:** 1.0
- **Stability:** 0.5
- **Similarity:** 0.75

## Step 3: Configure the Tool

Add a **Server Tool** (Function Calling):

### Tool Configuration

**Name:** `place_order`

**URL:** `https://your-domain.com/place_order` (or your ngrok URL)

**Method:** POST

**Description:** 
```
Place a customer order with items, quantities, and special requests. Call this when the customer has confirmed their order.
```

### Parameters Schema

Paste this exact JSON schema:

```json
{
  "type": "object",
  "properties": {
    "items": {
      "type": "array",
      "description": "List of ordered items with ID, name, and quantity",
      "items": {
        "type": "object",
        "properties": {
          "id": {
            "type": "integer",
            "description": "Menu item ID number"
          },
          "name": {
            "type": "string",
            "description": "Name of the menu item"
          },
          "quantity": {
            "type": "integer",
            "description": "Number of items ordered"
          }
        },
        "required": ["id", "name", "quantity"]
      }
    },
    "special_requests": {
      "type": "string",
      "description": "Any special requests from the customer (e.g., 'ingen lök', 'extra ost', 'starksås på sidan')"
    }
  },
  "required": ["items"]
}
```

### Tool Execution

- **When to call:** After customer confirms order
- **Headers:** (leave empty or add custom headers if needed)
- **Authentication:** None (or add API key if you implement it)

## Step 4: Phone Number Configuration

1. Go to "Phone Numbers" in Vapi dashboard
2. Buy a Swedish phone number or import your existing one
3. Assign the number to your "Gislegrillen Order Bot" assistant

## Step 5: Test the System

### Test Call Flow

1. Call your Vapi phone number
2. Say: "Hej, jag vill beställa en Hawaii och en Kebabpizza utan lök"
3. AI should:
   - Confirm the order
   - Ask about drinks
   - Repeat the order
   - Call the `place_order` tool
   - Confirm: "Tack för din beställning! Den är klar om 15 minuter."

### Check Results

- **Console:** Kitchen ticket should print
- **Dashboard:** Order should appear at http://localhost:8000/dashboard
- **Pushover:** Notification should be sent
- **orders.json:** Order should be saved

## Step 6: Webhook Configuration (Optional)

For advanced call tracking:

**Webhook URL:** `https://your-domain.com/vapi/webhook`

Events to subscribe:
- `call.started`
- `call.ended`
- `tool.called`

## Example Test Scenarios

### Scenario 1: Simple Order
```
Customer: "Hej, jag vill ha en fyra."
AI: "En Hawaii, okej. Vill du ha något att dricka till det?"
Customer: "Ja, en Coca-Cola."
AI: "Perfekt! Så det blir en Hawaii och en Coca-Cola. Stämmer det?"
Customer: "Ja."
AI: [Calls place_order] "Tack för din beställning! Den är klar om 15 minuter. Välkommen! Hejdå!"
```

### Scenario 2: Complex Order with Special Requests
```
Customer: "Jag vill beställa två Kebabpizzor utan lök och en Pepperoni med extra ost."
AI: "Okej, två Kebabpizzor utan lök och en Pepperoni med extra ost. Vill du ha något att dricka?"
Customer: "Två Fanta, tack."
AI: "Så det blir två Kebabpizzor utan lök, en Pepperoni med extra ost, och två Fanta. Stämmer det?"
Customer: "Ja, det stämmer."
AI: [Calls place_order] "Tack för din beställning! Den är klar om 15 minuter. Välkommen! Hejdå!"
```

### Scenario 3: Menu Inquiry
```
Customer: "Vad innehåller en Capricciosa?"
AI: "En Capricciosa innehåller tomatsås, ost, skinka och champinjoner. Kostar 98 kronor. Vill du beställa den?"
Customer: "Ja tack."
AI: "En Capricciosa, okej. Något mer?"
Customer: "Nej, det räcker."
AI: "Perfekt! Så det blir en Capricciosa. Stämmer det?"
Customer: "Ja."
AI: [Calls place_order] "Tack för din beställning! Den är klar om 15 minuter. Välkommen! Hejdå!"
```

## Troubleshooting

### AI not calling the tool
- Check that tool URL is correct and publicly accessible
- Verify tool schema matches exactly
- Check system prompt mentions the tool
- Enable Vapi debug logs

### Tool call fails
- Check server logs in console
- Verify FastAPI server is running
- Test endpoint directly with curl:
  ```bash
  curl -X POST https://your-domain.com/place_order \
    -H "Content-Type: application/json" \
    -d '{
      "items": [{"id": 4, "name": "Hawaii", "quantity": 1}],
      "special_requests": "Ingen lök"
    }'
  ```

### AI speaks English instead of Swedish
- Double-check system prompt is in Swedish
- Verify voice is set to Swedish (sv-SE)
- Check model temperature (should be 0.7)

### Orders not appearing
- Check console for errors
- Verify orders.json is writable
- Check dashboard at http://localhost:8000/dashboard
- Use browser dev tools to check for API errors

## Advanced Configuration

### Custom Domain
```bash
# Use a reverse proxy (nginx)
server {
    listen 80;
    server_name gislegrillen.yourdomain.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### SSL Certificate
```bash
# Use Let's Encrypt
sudo certbot --nginx -d gislegrillen.yourdomain.com
```

### Authentication
Add API key verification in main.py:
```python
from fastapi import Header, HTTPException

@app.post("/place_order")
async def place_order(request: PlaceOrderRequest, x_api_key: str = Header(None)):
    if x_api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=401, detail="Invalid API key")
    # ... rest of the code
```

## Production Checklist

- [ ] Server deployed with HTTPS
- [ ] Environment variables configured
- [ ] Pushover notifications tested
- [ ] Dashboard accessible
- [ ] Phone number configured in Vapi
- [ ] Test calls completed successfully
- [ ] Backup system for orders.json
- [ ] Monitoring/logging setup
- [ ] Error alerting configured

## Support

If you encounter issues:
1. Check server logs: `tail -f /var/log/gislegrillen.log`
2. Test API endpoints directly with curl
3. Enable Vapi debug mode
4. Check orders.json permissions
5. Verify all API keys are correct

---

**Ready to take orders!** 🍕📞

The system is designed to be autonomous. Once configured, it will:
- Answer calls automatically
- Take orders professionally
- Save orders persistently
- Notify you instantly
- Display everything on the dashboard

Just monitor the dashboard and mark orders as ready when they're done cooking!
