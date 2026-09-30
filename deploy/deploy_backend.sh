#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy_backend.sh  —  Run on VM2, VM3, VM4 to start the FastAPI backend
# Usage:  bash deploy_backend.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

APP_DIR="$HOME/AI-Pond-Planner/backend"
PORT=4000   # internal — LB proxies to this

cd "$APP_DIR"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then cp .env.example .env; fi
fi

# Detect Python executable (prefer ~/venv if present)
if [ -f "$HOME/venv/bin/python" ]; then
    PYTHON="$HOME/venv/bin/python"
elif [ -f "$HOME/.venv/bin/python" ]; then
    PYTHON="$HOME/.venv/bin/python"
else
    PYTHON="python3"
fi

echo "==> Using Python binary: $PYTHON"

# Ensure dependencies are installed
$PYTHON -m pip install -q -r requirements.txt 2>/dev/null || true

echo "==> Killing old server processes on port $PORT..."
pkill -9 -f "uvicorn app.main:app" 2>/dev/null || true
if command -v fuser >/dev/null 2>&1; then
    fuser -k ${PORT}/tcp 2>/dev/null || true
fi
sleep 1

LOG_FILE="$HOME/server_${PORT}.log"
echo "==> Starting uvicorn on port $PORT..."
nohup $PYTHON -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers 2 \
    --log-level info \
    > "$LOG_FILE" 2>&1 &

sleep 3

if curl -s "http://localhost:$PORT/health" >/dev/null 2>&1 || curl -s "http://localhost:$PORT/" >/dev/null 2>&1; then
    echo "✅ Backend successfully started and responding on port $PORT!"
else
    echo "⚠️ Backend start verification failed. Checking log tail ($LOG_FILE):"
    tail -n 25 "$LOG_FILE"
fi

