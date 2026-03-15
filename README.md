# CT Town Advisor

A voice-enabled AI advisor for Connecticut town data, built with **Gemini Live API**, **Streamlit**, and **Plotly**.

Residents, developers, and town officials can ask questions in natural language — by voice or text — and receive spoken answers plus live-rendered charts, all grounded in the official PDF documents you provide.

---

## Architecture

```
User (voice / text)
       │
       ▼
  Streamlit frontend  (app/main.py)
       │
       ├──► pdf_loader.py  ──► reads /data/*.pdf with PyMuPDF
       │          │
       │          └──► builds one large context string (no vector DB)
       │
       ├──► gemini_client.py ──► Gemini Live API session
       │          │               • sends audio or text
       │          │               • receives audio + return_chart() tool calls
       │
       └──► chart_builder.py ──► validates & themes Plotly JSON
                                  └──► rendered inline in Streamlit
```

---

## Quickstart

### 1. Clone & set up environment

```bash
git clone <repo-url>
cd ct-town-advisor

python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env and fill in GOOGLE_API_KEY (and GCS_BUCKET_NAME if using GCS)
```

### 3. Add PDF documents

Drop any number of `.pdf` files into the `/data` directory:

```
data/
  ct_budget_2024.pdf
  zoning_regulations.pdf
  demographics_report.pdf
```

Or configure `GCS_BUCKET_NAME` to sync them automatically from Google Cloud Storage on startup.

### 4. Run the app

```bash
streamlit run app/main.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Project Structure

```
ct-town-advisor/
├── app/
│   └── main.py              # Streamlit UI (text + voice modes)
├── src/
│   ├── pdf_loader.py        # PDF text extraction (PyMuPDF)
│   ├── gemini_client.py     # Gemini Live API session + chart tool
│   ├── gcs_loader.py        # Optional GCS PDF sync
│   ├── chart_builder.py     # Plotly JSON validation + CT theme
│   └── audio_utils.py       # PCM ↔ WAV helpers
├── data/                    # Place your PDF files here
├── infra/
│   ├── Dockerfile           # Multi-stage Docker build
│   ├── docker-compose.yml   # Local container dev
│   ├── cloudrun.yaml        # Cloud Run service spec
│   └── deploy.sh            # One-command GCP deploy script
├── .env.example
├── .gitignore
└── requirements.txt
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **No vector DB** | All PDF text is loaded directly into Gemini's context window — simpler architecture, no embedding pipeline needed |
| **Gemini Live API** | Native voice streaming with low latency; supports function calling mid-stream for chart JSON |
| **`return_chart` function call** | Gemini decides when a chart adds value and returns a Plotly spec; frontend renders it without any hardcoded chart logic |
| **PyMuPDF** | Fast, reliable PDF text extraction with no external dependencies |
| **Cloud Run** | Scales to zero, handles stateful WebSocket connections needed for Live API |

---

## Docker

```bash
# Local development
docker compose -f infra/docker-compose.yml up --build

# Production (Cloud Run)
./infra/deploy.sh YOUR_GCP_PROJECT_ID us-east1
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Yes | Gemini API key from Google AI Studio |
| `GCS_BUCKET_NAME` | No | GCS bucket containing PDFs under `pdfs/` prefix |
| `GEMINI_MODEL` | No | Override model (default: `gemini-2.0-flash-live-001`) |
