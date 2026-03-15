FROM python:3.11-slim

# System dependencies
# portaudio19-dev  — PyAudio mic streaming
# ffmpeg           — audio format conversion
# gcc / python3-dev — native extension builds (e.g. PyAudio)
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# Environment variables (no secrets here — injected at runtime via Secret Manager)
ENV PYTHONPATH=/app \
    STREAMLIT_SERVER_PORT=8080 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true

EXPOSE 8080

CMD ["streamlit", "run", "app/main.py", \
     "--server.port=8080", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
