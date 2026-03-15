#!/usr/bin/env bash
# start.sh — launch FastAPI + Streamlit + nginx inside the Cloud Run container
set -euo pipefail

export PYTHONPATH=/app

# ── 1. Start FastAPI WebSocket proxy on port 8081 ─────────────────────────
uvicorn api.main:app \
    --host 127.0.0.1 \
    --port 8081 \
    --workers 1 \
    --log-level warning &

UVICORN_PID=$!

# ── 2. Start Streamlit on port 8501 ───────────────────────────────────────
streamlit run app/main.py \
    --server.port=8501 \
    --server.address=127.0.0.1 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false &

STREAMLIT_PID=$!

# ── 3. Brief wait for both services to bind before nginx starts ───────────
sleep 3

# ── 4. Start nginx in foreground (keeps container alive for Cloud Run) ────
exec nginx -c /etc/nginx/nginx.conf -g 'daemon off;'
