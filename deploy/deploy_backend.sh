#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy_backend.sh  —  Run on VM2, VM3, VM4 to start the FastAPI backend
# Usage:  bash deploy_backend.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e
REPO="https://github.com/Aj1359/AI-Pond-Planner.git"
APP_DIR="$HOME/AI-Pond-Planner/backend"
VENV="$HOME/venv"
PORT=4000   # internal — LB proxies to this

echo "==> Pulling latest code..."
if [ -d "$HOME/AI-Pond-Planner" ]; then
    cd "$HOME/AI-Pond-Planner" && git pull origin main
else
    git clone --depth 1 "$REPO" "$HOME/AI-Pond-Planner"
fi

cd "$APP_DIR"

echo "==> Setting up Python venv..."
python3 -m venv "$VENV" || true
source "$VENV/bin/activate"
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "==> Copying .env if not present..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then cp .env.example .env; fi
    echo "  ⚠️  Edit $APP_DIR/.env with your SUPABASE_URL and SUPABASE_SERVICE_KEY"
fi

echo "==> Killing old server on port $PORT..."
pkill -f "uvicorn app.main:app" || true
sleep 1

echo "==> Starting uvicorn on port $PORT..."
nohup uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers 2 \
    --log-level info \
    > "$HOME/server_${PORT}.log" 2>&1 &

echo "  PID $! — logs at $HOME/server_${PORT}.log"
echo ""
echo "✅ Backend running on :$PORT"
echo "   Test: curl http://localhost:$PORT/"
