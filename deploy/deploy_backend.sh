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

APP_DIR="$HOME/AI-Pond-Planner/backend"
PORT=4000   # internal — LB proxies to this

cd "$APP_DIR"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then cp .env.example .env; fi
fi

echo "==> Killing old server processes..."
pkill -f "uvicorn" || true
fuser -k ${PORT}/tcp || true
sleep 1

echo "==> Starting uvicorn on port $PORT with system python3..."
nohup python3 -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers 2 \
    --log-level info \
    > "$HOME/server_${PORT}.log" 2>&1 &

sleep 2
echo "✅ Backend started on port $PORT"
curl -s http://localhost:$PORT/ || true
