FROM python:3.11-slim

# System dependencies
# nginx          — reverse proxy (routes :8080 → Streamlit :8501 and FastAPI :8081)
# portaudio19-dev — PyAudio (local dev only; no-op on Cloud Run)
# ffmpeg          — audio format conversion
# gcc / python3-dev — native extension builds
RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx \
        portaudio19-dev \
        ffmpeg \
        gcc \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies before copying source
# (layer cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy entire project
COPY . .

# Install nginx config and make start script executable
COPY infra/nginx.conf /etc/nginx/nginx.conf
RUN chmod +x infra/start.sh

# Environment variables (no secrets here — injected at runtime via Secret Manager)
ENV PYTHONPATH=/app \
    STREAMLIT_SERVER_HEADLESS=true

EXPOSE 8080

CMD ["/app/infra/start.sh"]
