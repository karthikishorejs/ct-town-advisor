#!/usr/bin/env bash
# dev.sh — run the full stack locally WITHOUT Docker
# Requires: nginx installed (brew install nginx on macOS)
# Usage: ./infra/dev.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"

# Load .env
ENV_FILE="$ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

export PYTHONPATH="$ROOT"
export K_SERVICE="local-dev"   # makes app.main use the WebSocket voice component
export PYTHONUNBUFFERED=1      # flush Python print() immediately so logs are visible

cd "$ROOT"

# ── Kill any leftovers from previous run ───────────────────────────────────
pkill -f "uvicorn api.main:app" 2>/dev/null || true
pkill -f "streamlit run app/main.py" 2>/dev/null || true
pkill -f "nginx.*infra/dev-nginx.conf" 2>/dev/null || true

# ── Write a temp nginx config pointing at local ports ─────────────────────
DEV_NGINX_CONF="/tmp/penny-dev-nginx.conf"
cat > "$DEV_NGINX_CONF" <<'NGINX'
worker_processes 1;
error_log /dev/stderr warn;
pid /tmp/penny-nginx.pid;
events { worker_connections 256; }
http {
    client_body_temp_path /tmp/nginx-client-body;
    proxy_temp_path       /tmp/nginx-proxy;
    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }
    server {
        listen 8080;
        location /ws/ {
            proxy_pass         http://127.0.0.1:8081;
            proxy_http_version 1.1;
            proxy_set_header   Upgrade    $http_upgrade;
            proxy_set_header   Connection $connection_upgrade;
            proxy_read_timeout 3600s;
        }
        location / {
            proxy_pass         http://127.0.0.1:8501;
            proxy_http_version 1.1;
            proxy_set_header   Upgrade    $http_upgrade;
            proxy_set_header   Connection $connection_upgrade;
            proxy_read_timeout 3600s;
        }
    }
}
NGINX

# ── Start services ─────────────────────────────────────────────────────────
echo "▶ Starting FastAPI on :8081…"
uvicorn api.main:app --host 127.0.0.1 --port 8081 --log-level info &
UVICORN_PID=$!

echo "▶ Starting Streamlit on :8501…"
streamlit run app/main.py \
    --server.port=8501 \
    --server.address=127.0.0.1 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false &
STREAMLIT_PID=$!

sleep 3

echo "▶ Starting nginx on :8080…"
nginx -c "$DEV_NGINX_CONF" -g 'daemon off;' &
NGINX_PID=$!

echo ""
echo "✅ Penny is running at  http://localhost:8080"
echo "   FastAPI   → :8081"
echo "   Streamlit → :8501"
echo "   Press Ctrl-C to stop all services."
echo ""

# ── Cleanup on exit ────────────────────────────────────────────────────────
trap "echo 'Stopping…'; kill $UVICORN_PID $STREAMLIT_PID $NGINX_PID 2>/dev/null; exit 0" INT TERM

wait
