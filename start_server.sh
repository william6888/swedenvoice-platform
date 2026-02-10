#!/bin/bash

# Gislegrillen Server Startup Script
# Detta script startar FastAPI-servern

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                                                              ║"
echo "║     🍕 Startar Gislegrillen Beställningssystem 🍕           ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Kontrollera om Python är installerat
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 är inte installerat!"
    exit 1
fi

# Kontrollera om dependencies är installerade
echo "📦 Kontrollerar dependencies..."
pip list | grep fastapi > /dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Dependencies saknas. Installerar..."
    pip install -r requirements.txt
fi

echo ""
echo "🚀 Startar FastAPI-server på port 8000..."
echo "📊 Dashboard kommer vara tillgänglig på: http://localhost:8000/dashboard"
echo ""
echo "💡 Tips: Håll denna terminal öppen!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Starta servern
python3 main.py
