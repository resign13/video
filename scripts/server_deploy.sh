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
NODE_MAJOR="0"
if command -v node >/dev/null 2>&1; then
  NODE_MAJOR="$(node -v | sed -E 's/^v([0-9]+).*/\1/')"
fi
if ! command -v npm >/dev/null 2>&1 || [ "${NODE_MAJOR:-0}" -lt 20 ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y ca-certificates curl gnupg
  # Ubuntu 22.04 apt 源自带的 Node 12 会与 NodeSource Node 20 冲突，先移除旧开发包。
  apt-get remove -y npm nodejs libnode-dev nodejs-doc || true
  apt-get -f install -y || true
  mkdir -p /etc/apt/keyrings
  rm -f /etc/apt/keyrings/nodesource.gpg
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list
  apt-get update
  apt-get install -y nodejs
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
