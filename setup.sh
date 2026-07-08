#!/bin/bash
# SmartScrape Pro — Quick Setup Script
set -e

echo "🕷️  SmartScrape Pro — Setup"
echo "================================"

# Check Python 3.10+
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✅ Python $python_version"

# Install deps
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt -q

# Playwright browsers
echo "🎭 Installing Playwright Chromium..."
playwright install chromium --with-deps 2>/dev/null || playwright install chromium

# Create dirs
echo "📁 Creating directories..."
mkdir -p database logs exports/uploads config

# Copy .env if not exists
if [ ! -f "config/.env" ]; then
    cp config/.env.example config/.env
    echo "📝 Created config/.env — please update with your credentials!"
else
    echo "✅ config/.env exists"
fi

echo ""
echo "================================"
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit config/.env (add Stripe keys, admin credentials)"
echo "  2. python run.py --mode dev"
echo "  3. Open http://localhost:8000/api/docs"
echo "  4. Login at frontend/templates/auth/login.html"
echo ""
echo "For production with Docker:"
echo "  docker-compose up -d"
