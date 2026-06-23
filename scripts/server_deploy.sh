#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/video}"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"

cd "$APP_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  apt-get update
  apt-get install -y python3 python3-venv python3-pip
fi
if ! command -v nginx >/dev/null 2>&1; then
  apt-get update
  apt-get install -y nginx
fi
if ! command -v npm >/dev/null 2>&1; then
  apt-get update
  apt-get install -y nodejs npm
fi

python3 -m venv "$BACKEND_DIR/.venv"
"$BACKEND_DIR/.venv/bin/python" -m pip install --upgrade pip
"$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt" gunicorn

if [ ! -f "$BACKEND_DIR/.env" ]; then
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
fi

cd "$FRONTEND_DIR"
npm ci || npm install
npm run build

cp "$APP_DIR/deploy/video-web.service" /etc/systemd/system/video-web.service
cp "$APP_DIR/deploy/nginx-video.conf" /etc/nginx/sites-available/video
ln -sf /etc/nginx/sites-available/video /etc/nginx/sites-enabled/video
rm -f /etc/nginx/sites-enabled/default

systemctl daemon-reload
systemctl enable video-web.service
systemctl restart video-web.service
nginx -t
systemctl reload nginx || systemctl restart nginx

echo "deployed ok"
systemctl --no-pager --full status video-web.service | sed -n '1,12p'
