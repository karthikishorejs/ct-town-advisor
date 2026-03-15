#!/usr/bin/env bash
# deploy.sh — Build and deploy CT Town Advisor to Google Cloud Run
# Usage: ./infra/deploy.sh
set -euo pipefail

# ── 1. Check prerequisites ────────────────────────────────────────────────────
if ! command -v gcloud &>/dev/null; then
  echo "❌ gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install"
  exit 1
fi

if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | grep -q "."; then
  echo "❌ Not authenticated. Run: gcloud auth login"
  exit 1
fi

# ── 2. Load project ID from .env ──────────────────────────────────────────────
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -v '^#' .env | grep '=')
  set +a
fi

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="us-central1"
SERVICE="ct-town-advisor"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "❌ Could not determine PROJECT_ID. Set GOOGLE_CLOUD_PROJECT in .env or run:"
  echo "   gcloud config set project YOUR_PROJECT_ID"
  exit 1
fi

echo "▶ Project : ${PROJECT_ID}"
echo "▶ Region  : ${REGION}"
echo "▶ Service : ${SERVICE}"
echo ""

# Set active gcloud project
gcloud config set project "${PROJECT_ID}" --quiet

# ── 3. Enable required APIs ──────────────────────────────────────────────────
echo "▶ Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  --project="${PROJECT_ID}" --quiet
echo "✅ APIs enabled."
echo ""

# ── 4. Create GOOGLE_API_KEY secret if it doesn't exist ──────────────────────
if [[ -z "${GOOGLE_API_KEY:-}" ]]; then
  echo "⚠️  GOOGLE_API_KEY not set in .env — skipping secret creation."
  echo "   Run ./infra/setup_secrets.sh first if this is a fresh deployment."
else
  if ! gcloud secrets describe GOOGLE_API_KEY --project="${PROJECT_ID}" &>/dev/null; then
    echo "▶ Creating GOOGLE_API_KEY secret in Secret Manager..."
    printf '%s' "${GOOGLE_API_KEY}" | gcloud secrets create GOOGLE_API_KEY \
      --project="${PROJECT_ID}" \
      --data-file=-
    echo "✅ Secret created."
  else
    echo "✅ Secret GOOGLE_API_KEY already exists."
  fi

  # Grant Cloud Build SA access (needed to pass secret into Cloud Run at deploy time)
  PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
  CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
  CR_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

  for sa in "${CB_SA}" "${CR_SA}"; do
    gcloud secrets add-iam-policy-binding GOOGLE_API_KEY \
      --project="${PROJECT_ID}" \
      --member="serviceAccount:${sa}" \
      --role="roles/secretmanager.secretAccessor" \
      --quiet 2>/dev/null || true
  done
  echo "✅ Secret access granted."
fi
echo ""

# ── 5. Submit build and deploy ───────────────────────────────────────────────
echo "▶ Submitting Cloud Build (this may take a few minutes)..."
gcloud builds submit \
  --config=infra/cloudbuild.yaml \
  --project="${PROJECT_ID}" \
  .

# ── 6. Print service URL ─────────────────────────────────────────────────────
SERVICE_URL=$(gcloud run services describe "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(status.url)" 2>/dev/null || echo "")

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  ✅  Deployment complete!                    ║"
echo "╠══════════════════════════════════════════════╣"
if [[ -n "${SERVICE_URL}" ]]; then
  echo "║  🌐  ${SERVICE_URL}"
fi
echo "╚══════════════════════════════════════════════╝"
