#!/usr/bin/env bash
# setup_secrets.sh — One-time Secret Manager setup for CT Town Advisor
# Run this once before the first deployment.
# Usage: ./infra/setup_secrets.sh  (from any directory)
set -euo pipefail

# ── Resolve project root from script location (works from any CWD) ───────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
ENV_FILE="${PROJECT_ROOT}/.env"

# ── Load .env ─────────────────────────────────────────────────────────────────
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "❌ .env not found at ${ENV_FILE}"
  echo "   Copy .env.example → .env and fill in your values."
  exit 1
fi

# set -a auto-exports every variable that gets set; source reads .env as bash
set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
if [[ -z "${PROJECT_ID}" ]]; then
  echo "❌ GOOGLE_CLOUD_PROJECT not set in .env"
  exit 1
fi

if [[ -z "${GOOGLE_API_KEY:-}" ]]; then
  echo "❌ GOOGLE_API_KEY not set in .env"
  exit 1
fi

echo "▶ Project: ${PROJECT_ID}"
echo ""

# ── 1. Enable Secret Manager API ─────────────────────────────────────────────
echo "▶ Enabling Secret Manager API..."
gcloud services enable secretmanager.googleapis.com \
  --project="${PROJECT_ID}" --quiet
echo "✅ Secret Manager API enabled."
echo ""

# ── 2. Create or update GOOGLE_API_KEY secret ────────────────────────────────
if gcloud secrets describe GOOGLE_API_KEY --project="${PROJECT_ID}" &>/dev/null; then
  echo "▶ Secret GOOGLE_API_KEY already exists — adding new version..."
  printf '%s' "${GOOGLE_API_KEY}" | gcloud secrets versions add GOOGLE_API_KEY \
    --project="${PROJECT_ID}" \
    --data-file=-
  echo "✅ New secret version added."
else
  echo "▶ Creating secret GOOGLE_API_KEY..."
  printf '%s' "${GOOGLE_API_KEY}" | gcloud secrets create GOOGLE_API_KEY \
    --project="${PROJECT_ID}" \
    --replication-policy="automatic" \
    --data-file=-
  echo "✅ Secret created."
fi
echo ""

# ── 3. Grant access to Cloud Run and Cloud Build service accounts ────────────
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")

# Cloud Run runtime SA  — reads the secret at container startup
CR_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
# Cloud Build SA        — needs access to pass --set-secrets during gcloud run deploy
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

echo "▶ Granting secretAccessor to Cloud Run SA  (${CR_SA})..."
gcloud secrets add-iam-policy-binding GOOGLE_API_KEY \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${CR_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet
echo "✅ Cloud Run SA granted."

echo "▶ Granting secretAccessor to Cloud Build SA (${CB_SA})..."
gcloud secrets add-iam-policy-binding GOOGLE_API_KEY \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${CB_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet
echo "✅ Cloud Build SA granted."
echo ""

echo "╔══════════════════════════════════════════════════╗"
echo "║  ✅  Secret setup complete!                      ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║  Secret name : GOOGLE_API_KEY                    ║"
echo "║  Project     : ${PROJECT_ID}"
echo "║  Access granted to:                              ║"
echo "║    ${CR_SA} (Cloud Run)"
echo "║    ${CB_SA} (Cloud Build)"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "Next step: ./infra/deploy.sh"
