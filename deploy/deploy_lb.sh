#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy_lb.sh  —  Run on VM1 (stu5_sys1) to set up nginx load balancer
# ─────────────────────────────────────────────────────────────────────────────
set -e
REPO="https://github.com/Aj1359/AI-Pond-Planner.git"
FRONTEND_DIR="/var/www/pond_planner/frontend"

echo "==> Installing nginx..."
sudo apt-get update -qq
sudo apt-get install -y nginx

echo "==> Copying nginx config..."
sudo cp nginx_lb.conf /etc/nginx/nginx.conf

echo "==> Creating cache dir..."
sudo mkdir -p /var/cache/nginx/pond

echo "==> Deploying frontend static files..."
sudo mkdir -p "$FRONTEND_DIR"
if [ -d "/tmp/AI-Pond-Planner" ]; then rm -rf /tmp/AI-Pond-Planner; fi
git clone --depth 1 "$REPO" /tmp/AI-Pond-Planner
sudo cp -r /tmp/AI-Pond-Planner/frontend/* "$FRONTEND_DIR/"

echo "==> Testing nginx config..."
sudo nginx -t

echo "==> Starting / reloading nginx..."
sudo systemctl enable nginx
sudo systemctl restart nginx

echo ""
echo "✅ Load balancer running on port 4218"
echo "   Frontend: http://\$(hostname -I | awk '{print \$1}'):4218/ui/"
echo "   Health:   http://\$(hostname -I | awk '{print \$1}'):4218/health"
