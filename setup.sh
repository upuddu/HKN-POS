#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# HKN POS — One-shot setup script
# Run:  bash setup.sh
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "╔══════════════════════════════════════╗"
echo "║   HKN POS — Setup                    ║"
echo "╚══════════════════════════════════════╝"

# ── 1. Python check ──────────────────────────────────────────────
PYTHON=""
for candidate in python3.10 python3.11 python3.12 python3.13 python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌  Python 3.10+ not found. Please install Python first."
    exit 1
fi

echo "✅  Using Python: $PYTHON ($($PYTHON --version 2>&1))"

# ── 2. Virtual environment ───────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "📦  Creating virtual environment..."
    $PYTHON -m venv .venv
fi

source .venv/bin/activate
echo "✅  Virtual environment activated: $(which python)"

# ── 3. Install dependencies ──────────────────────────────────────
echo "📦  Installing dependencies..."
pip install -e ".[dev]" --quiet

# ── 4. .env configuration ────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "📝  Creating .env from template..."
    cp .env.example .env
    echo ""
    echo "⚠️   IMPORTANT: Edit .env to fill in your credentials:"
    echo "     - EMAIL_ADDRESS (your Purdue email)"
    echo "     - EMAIL_PASSWORD (app password)"
    echo "     - API_PASSKEY (shared secret for the external server)"
    echo "     - WEBHOOK_URL (external server's interrupt endpoint)"
    echo ""
else
    echo "✅  .env already exists"
fi

# ── 5. Create directories ────────────────────────────────────────
mkdir -p downloads
echo "✅  downloads/ directory ready"

# ── 6. Initialize database ───────────────────────────────────────
python -c "
from hkn_pos.storage import OrderStore
from hkn_pos.comm_log import CommLog
import os
db = os.getenv('DB_PATH', 'hkn_pos.db')
OrderStore(db)
CommLog(db)
print(f'✅  Database initialized: {db}')
"

# ── 7. Run tests ─────────────────────────────────────────────────
echo "🧪  Running tests..."
python -m pytest tests/ -q

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   Setup complete!                    ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your credentials"
echo "  2. Start the server:  ./hknctl start"
echo "  3. Check status:      ./hknctl status"
echo "  4. View DB:           ./hknctl db"
echo "  5. View logs:         ./hknctl logs"
echo "  6. Stop:              ./hknctl stop"
