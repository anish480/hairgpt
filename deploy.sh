#!/usr/bin/env bash
set -euo pipefail

PROJECT="hairgpt-496305"
REGION="asia-south1"
SERVICE="hairgpt-preview"
REPO="hairgpt-repo"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/${SERVICE}:latest"

echo "=== 1/6  Enabling APIs ==="
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  --project="${PROJECT}"

echo "=== 2/6  Creating Artifact Registry repo (if needed) ==="
gcloud artifacts repositories describe "${REPO}" \
  --location="${REGION}" --project="${PROJECT}" 2>/dev/null \
|| gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT}"

echo "=== 3/6  Building container image ==="
gcloud builds submit \
  --tag="${IMAGE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  .

echo "=== 4/6  Getting default compute service account ==="
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
echo "Service account: ${SA}"

echo "=== 5/6  Granting IAM roles to service account ==="
for ROLE in roles/aiplatform.user roles/secretmanager.secretAccessor roles/cloudsql.client; do
  gcloud projects add-iam-policy-binding "${PROJECT}" \
    --member="serviceAccount:${SA}" \
    --role="${ROLE}" \
    --condition=None \
    --quiet 2>/dev/null || true
done

echo "=== 6/6  Deploying to Cloud Run ==="
gcloud run deploy "${SERVICE}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT},GCP_LOCATION=${REGION}" \
  --add-cloudsql-instances="${PROJECT}:${REGION}:hairgpt-db" \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --timeout=120

URL=$(gcloud run services describe "${SERVICE}" --region="${REGION}" --project="${PROJECT}" --format='value(status.url)')
echo ""
echo "=== Done! ==="
echo "Preview:  ${URL}/preview"
echo "API:      ${URL}/health"
