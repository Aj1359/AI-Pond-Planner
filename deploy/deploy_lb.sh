#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy_lb.sh  —  Run on VM1 (stu5_sys1) to set up nginx load balancer
# ─────────────────────────────────────────────────────────────────────────────
set -e
FRONTEND_DIR="/var/www/pond_planner/frontend"

echo "==> Installing nginx..."
sudo apt-get update -qq
sudo apt-get install -y nginx psmisc

echo "==> Clearing old processes on port 4217 & 80..."
sudo pkill -9 nginx || true
sudo fuser -k 4217/tcp || true
sudo fuser -k 80/tcp || true
sudo pkill -f uvicorn || true
sleep 1

echo "==> Copying nginx config..."
sudo rm -f /etc/nginx/sites-enabled/default /etc/nginx/sites-available/default
sudo cp nginx_lb.conf /etc/nginx/nginx.conf

echo "==> Creating cache dir..."
sudo mkdir -p /var/cache/nginx/pond

echo "==> Deploying frontend static files..."
sudo mkdir -p "$FRONTEND_DIR"
sudo cp -r /home/student/AI-Pond-Planner/frontend/* "$FRONTEND_DIR/"
sudo chmod -R 755 /var/www/pond_planner

echo "==> Testing nginx config..."
sudo nginx -t

echo "==> Starting nginx service..."
sudo service nginx restart || sudo service nginx start || sudo nginx

echo ""
echo "✅ Load balancer running!"
echo "   Frontend: http://10.1.75.51:4217/ui/"
echo "   Health:   http://10.1.75.51:4217/health"
