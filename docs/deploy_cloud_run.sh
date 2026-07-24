#!/usr/bin/env bash
# Deploys backend/Dockerfile to Google Cloud Run.
#
# NOT RUN AS PART OF THIS SESSION'S DEPLOYMENT WORK: this machine has no
# `gcloud` CLI installed and no authenticated GCP account/billing access
# (see /docs/BLOCKERS.md). This script is the exact, ready-to-run command
# sequence for whoever has that access - the Dockerfile it deploys has
# already been built and smoke-tested locally (real `docker build` +
# `docker run` + `GET /health` returning 200 from the host, i.e. from
# outside the container - see PROGRESS.md Phase 10.1).
#
# Usage:
#   GCP_PROJECT_ID=your-project \
#   GCP_REGION=us-central1 \
#   SUPABASE_URL=https://xxxx.supabase.co \
#   SUPABASE_ANON_KEY=... \
#   SUPABASE_SERVICE_ROLE_KEY=... \
#   DATABASE_URL=postgresql://... \
#   ALLOWED_ORIGINS=https://your-web-app-hosting-domain \
#     ./docs/deploy_cloud_run.sh
set -euo pipefail

: "${GCP_PROJECT_ID:?set GCP_PROJECT_ID}"
: "${GCP_REGION:=us-central1}"
: "${SUPABASE_URL:?set SUPABASE_URL (production project)}"
: "${SUPABASE_ANON_KEY:?set SUPABASE_ANON_KEY (production project)}"
: "${SUPABASE_SERVICE_ROLE_KEY:?set SUPABASE_SERVICE_ROLE_KEY (production project)}"
: "${DATABASE_URL:?set DATABASE_URL (production Postgres connection string)}"
: "${ALLOWED_ORIGINS:?set ALLOWED_ORIGINS (comma-separated web hosting origin(s))}"

SERVICE_NAME="${CLOUD_RUN_SERVICE_NAME:-exam-scanner-backend}"
REPO="backend"
IMAGE="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${REPO}/${SERVICE_NAME}:$(date +%Y%m%d-%H%M%S)"

gcloud config set project "$GCP_PROJECT_ID"

# CLAUDE.md Section 8's env vars are secrets - stored in Secret Manager, not
# passed as plain --set-env-vars, and not hardcoded anywhere in this repo.
# `--set-secrets` mounts each as an env var sourced from the named secret's
# latest version at container start.
for secret_name in supabase-url supabase-anon-key supabase-service-role-key database-url; do
  gcloud secrets describe "$secret_name" >/dev/null 2>&1 || \
    gcloud secrets create "$secret_name" --replication-policy=automatic
done
printf '%s' "$SUPABASE_URL" | gcloud secrets versions add supabase-url --data-file=-
printf '%s' "$SUPABASE_ANON_KEY" | gcloud secrets versions add supabase-anon-key --data-file=-
printf '%s' "$SUPABASE_SERVICE_ROLE_KEY" | gcloud secrets versions add supabase-service-role-key --data-file=-
printf '%s' "$DATABASE_URL" | gcloud secrets versions add database-url --data-file=-

gcloud builds submit "$(dirname "$0")/../backend" --tag "$IMAGE"

# Autoscaling: min 0 (scale-to-zero when idle, since this is a low-traffic
# professor tool, not a high-QPS service) up to 10; Cloud Run's own health
# check is HTTP GET / (readiness) which Dockerfile's uvicorn already serves
# on every route including /health - --startup-cp-boost not needed at this
# scale.
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --region "$GCP_REGION" \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 10 \
  --port 8080 \
  --set-env-vars "ENV=production,ALLOWED_ORIGINS=${ALLOWED_ORIGINS}" \
  --set-secrets "SUPABASE_URL=supabase-url:latest,SUPABASE_ANON_KEY=supabase-anon-key:latest,SUPABASE_SERVICE_ROLE_KEY=supabase-service-role-key:latest,DATABASE_URL=database-url:latest"

SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" --region "$GCP_REGION" --format 'value(status.url)')"
echo "Deployed: $SERVICE_URL"
echo "Verifying /health from an external client..."
curl -sf -o /dev/null -w "GET ${SERVICE_URL}/health -> HTTP %{http_code}\n" "${SERVICE_URL}/health"
