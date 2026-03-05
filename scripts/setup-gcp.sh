#!/bin/bash
# SubsGen — GCP Cloud Run setup
# Run this once to create project, enable APIs, and get a service account key for GitHub Actions.
# Prerequisites: gcloud CLI installed and logged in (gcloud auth login)

set -e

PROJECT_ID="${GCP_PROJECT_ID:-subsgen-backend}"
PROJECT_NAME="SubsGen Backend"
REGION="${GCP_REGION:-us-central1}"
SA_NAME="github-deploy"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=== SubsGen GCP Setup ==="
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# 1. Create project (or use existing)
if gcloud projects describe "$PROJECT_ID" &>/dev/null; then
  echo "[1/6] Project $PROJECT_ID already exists"
else
  echo "[1/6] Creating project $PROJECT_ID..."
  gcloud projects create "$PROJECT_ID" --name="$PROJECT_NAME"
fi
gcloud config set project "$PROJECT_ID"

# 2. Enable billing (required for Cloud Run — user must do this manually if new project)
echo "[2/6] Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com

# 3. Create Artifact Registry repo for Docker images
echo "[3/6] Creating Artifact Registry repository..."
gcloud artifacts repositories create subsgen \
  --repository-format=docker \
  --location="$REGION" \
  --description="SubsGen backend images" \
  2>/dev/null || echo "  (repository may already exist)"

# 4. Create service account for GitHub Actions
echo "[4/6] Creating service account $SA_EMAIL..."
gcloud iam service-accounts create "$SA_NAME" \
  --display-name="GitHub Actions Deploy" \
  2>/dev/null || echo "  (service account may already exist)"

# 5. Grant roles to service account
echo "[5/6] Granting IAM roles..."
for role in run.admin artifactregistry.writer iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/${role}" \
    --quiet
done

# 6. Create and download key
KEY_FILE="github-deploy-key.json"
echo "[6/6] Creating key file $KEY_FILE..."
gcloud iam service-accounts keys create "$KEY_FILE" \
  --iam-account="$SA_EMAIL"

echo ""
echo "=== Setup complete ==="
echo ""
echo "1. Add this secret to GitHub:"
echo "   Repo → Settings → Secrets and variables → Actions"
echo "   New repository secret: GCP_SA_KEY"
echo "   Value: paste the entire contents of $KEY_FILE"
echo ""
echo "2. Add these repository variables (or use secrets):"
echo "   GCP_PROJECT_ID = $PROJECT_ID"
echo "   GCP_REGION     = $REGION"
echo ""
echo "3. Add GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_API_KEY_3 as GitHub secrets"
echo "   (or GROQ_API_KEY) — these will be passed to Cloud Run"
echo ""
echo "4. Delete $KEY_FILE after adding to GitHub (do not commit it)"
echo "   rm $KEY_FILE"
echo ""
echo "5. Push to main to trigger deploy"
echo ""
