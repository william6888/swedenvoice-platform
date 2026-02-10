#!/bin/bash

# Gislegrillen ngrok Tunnel Script
# Detta script exponerar din lokala server till internet

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                                                              ║"
echo "║        🌐 Startar ngrok tunnel till port 8000 🌐            ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Kontrollera om ngrok är installerat
if ! command -v ngrok &> /dev/null; then
    echo "❌ ngrok är inte installerat!"
    exit 1
fi

echo "🔧 Kontrollerar om servern körs på port 8000..."
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo "✅ Server detekterad på port 8000"
else
    echo "⚠️  VARNING: Ingen server körs på port 8000!"
    echo "   Starta servern först med: ./start_server.sh"
    echo ""
    echo "   Fortsätter ändå..."
fi

echo ""
echo "🚀 Startar ngrok tunnel..."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 VIKTIGT: Kopiera den HTTPS-URL som visas nedan!"
echo "    Den ser ut typ: https://abc123.ngrok-free.app"
echo ""
echo "    Använd denna URL i Vapi-konfigurationen:"
echo "    https://DIN-URL.ngrok-free.app/place_order"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 Tryck Ctrl+C för att stoppa tunneln"
echo ""

# Starta ngrok
ngrok http 8000
