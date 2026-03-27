#!/bin/bash
# One-command DigitalOcean server setup for Law Firm AI
# Run as root on a fresh Ubuntu 22.04 droplet:
#   curl -fsSL https://raw.githubusercontent.com/YOUR_REPO/main/scripts/deploy.sh | bash

set -euo pipefail

APP_DIR="/opt/law-firm-ai"
REPO_URL="https://github.com/YOUR_GITHUB_ORG/Law-Firm-AI.git"

echo "=== Installing system dependencies ==="
apt-get update -qq
apt-get install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx s3cmd curl git

echo "=== Starting Docker ==="
systemctl enable docker
systemctl start docker

echo "=== Cloning repository ==="
if [ -d "${APP_DIR}" ]; then
    cd "${APP_DIR}" && git pull
else
    git clone "${REPO_URL}" "${APP_DIR}"
fi

cd "${APP_DIR}"

echo "=== Setting up environment ==="
if [ ! -f .env ]; then
    cp .env.example .env
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/change-me-to-a-long-random-string/${JWT_SECRET}/" .env
    echo ""
    echo ">>> IMPORTANT: Edit .env and fill in your ANTHROPIC_API_KEY before starting"
    echo ">>> Run: nano ${APP_DIR}/.env"
fi

echo "=== Setting file permissions ==="
chmod 600 .env
chmod +x scripts/*.sh

echo "=== Building and starting containers ==="
docker compose build
docker compose up -d

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env:          nano ${APP_DIR}/.env"
echo "  2. Restart app:        cd ${APP_DIR} && docker compose restart"
echo "  3. Set up SSL:         certbot --nginx -d YOUR_DOMAIN"
echo "  4. Deploy Nginx conf:  cp ${APP_DIR}/nginx/law-firm-ai.conf /etc/nginx/sites-enabled/"
echo "                         sed -i 's/YOUR_DOMAIN/yourdomain.com/g' /etc/nginx/sites-enabled/law-firm-ai.conf"
echo "                         nginx -t && systemctl reload nginx"
echo "  5. Set up backups:     crontab -e  (add: 0 2 * * * ${APP_DIR}/scripts/backup.sh)"
echo "  6. Enable DO backups:  Enable 'Backups' on your Droplet in the DigitalOcean dashboard"
echo ""
echo "App running at: http://$(curl -s ifconfig.me):8501"
