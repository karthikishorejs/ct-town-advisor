#!/usr/bin/env bash
# setup_secrets.sh — One-time IAM + Secret Manager setup for CT Town Advisor
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

USER_EMAIL="$(gcloud config get-value account 2>/dev/null)"
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")

echo "▶ Project : ${PROJECT_ID}"
echo "▶ User    : ${USER_EMAIL}"
echo ""

# ── 1. Enable required APIs ───────────────────────────────────────────────────
echo "▶ Enabling APIs..."
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  --project="${PROJECT_ID}" --quiet
echo "✅ APIs enabled."
echo ""

# ── 2. Grant your user account the roles needed to deploy ────────────────────
# These roles are required for gcloud builds submit + gcloud run deploy.
# Safe to re-run — add-iam-policy-binding is idempotent.
echo "▶ Granting deployment roles to ${USER_EMAIL}..."

DEPLOY_ROLES=(
  "roles/cloudbuild.builds.editor"   # submit Cloud Build jobs
  "roles/storage.admin"              # upload build source to GCS
  "roles/run.admin"                  # deploy / manage Cloud Run services
  "roles/iam.serviceAccountUser"     # act-as Cloud Run / Cloud Build SAs
  "roles/artifactregistry.writer"    # push Docker images
)

for role in "${DEPLOY_ROLES[@]}"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="user:${USER_EMAIL}" \
    --role="${role}" \
    --quiet 2>/dev/null && echo "  ✅ ${role}" || echo "  ⚠️  ${role} (may already be set or requires Owner)"
done
echo ""

# ── 3. Create or update GOOGLE_API_KEY secret ────────────────────────────────
echo "▶ Setting up GOOGLE_API_KEY secret..."
if gcloud secrets describe GOOGLE_API_KEY --project="${PROJECT_ID}" &>/dev/null; then
  echo "▶ Secret already exists — adding new version..."
  printf '%s' "${GOOGLE_API_KEY}" | gcloud secrets versions add GOOGLE_API_KEY \
    --project="${PROJECT_ID}" \
    --data-file=-
  echo "✅ New secret version added."
else
  printf '%s' "${GOOGLE_API_KEY}" | gcloud secrets create GOOGLE_API_KEY \
    --project="${PROJECT_ID}" \
    --replication-policy="automatic" \
    --data-file=-
  echo "✅ Secret created."
fi
echo ""

# ── 4. Grant secret access to Cloud Run and Cloud Build service accounts ──────
CR_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

echo "▶ Granting secretAccessor to service accounts..."
for sa in "${CR_SA}" "${CB_SA}"; do
  gcloud secrets add-iam-policy-binding GOOGLE_API_KEY \
    --project="${PROJECT_ID}" \
    --member="serviceAccount:${sa}" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet 2>/dev/null && echo "  ✅ ${sa}" || echo "  ⚠️  ${sa} (may not exist yet — re-run after first build)"
done
echo ""

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅  Setup complete!                                     ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Project  : ${PROJECT_ID}"
echo "║  Secret   : GOOGLE_API_KEY (latest version)              ║"
echo "║  IAM      : deployment roles granted to ${USER_EMAIL}"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Next step: ./infra/deploy.sh"
