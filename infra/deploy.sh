#!/usr/bin/env bash
# deploy.sh — Build, push, and deploy CT Town Advisor to Cloud Run
# Usage: ./infra/deploy.sh [PROJECT_ID] [REGION]

set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project)}"
REGION="${2:-us-east1}"
IMAGE="gcr.io/${PROJECT_ID}/ct-town-advisor"

echo "▶ Project : ${PROJECT_ID}"
echo "▶ Region  : ${REGION}"
echo "▶ Image   : ${IMAGE}"

# Build and push using Cloud Build (no local Docker required)
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE}" \
  --file=infra/Dockerfile \
  .

# Create secrets if they don't already exist
create_secret_if_missing() {
  local name="$1" value="$2"
  if ! gcloud secrets describe "${name}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "Creating secret: ${name}"
    echo -n "${value}" | gcloud secrets create "${name}" \
      --project="${PROJECT_ID}" \
      --data-file=-
  else
    echo "Secret already exists: ${name}"
  fi
}

create_secret_if_missing "ct-advisor-secrets" "placeholder"

# Deploy to Cloud Run
gcloud run services replace infra/cloudrun.yaml \
  --project="${PROJECT_ID}" \
  --region="${REGION}"

# Make the service publicly accessible
gcloud run services add-iam-policy-binding ct-town-advisor \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --member="allUsers" \
  --role="roles/run.invoker"

SERVICE_URL=$(gcloud run services describe ct-town-advisor \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(status.url)")

echo ""
echo "✅ Deployed successfully!"
echo "   Service URL: ${SERVICE_URL}"
