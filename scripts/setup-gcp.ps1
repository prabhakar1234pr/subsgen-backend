# SubsGen — GCP Cloud Run setup
# Run this once to create project, enable APIs, and get a service account key for GitHub Actions.
# Prerequisites: gcloud CLI installed and logged in (gcloud auth login)
# Run: .\scripts\setup-gcp.ps1

$ErrorActionPreference = "Stop"

# Use a unique project ID — GCP project IDs are globally unique.
# If subsgen-backend is taken, use e.g. subsgen-backend-YOURNAME or subsgen-12345
$PROJECT_ID = if ($env:GCP_PROJECT_ID) { $env:GCP_PROJECT_ID } else { "subsgen-backend" }
$PROJECT_NAME = "SubsGen Backend"
$REGION = if ($env:GCP_REGION) { $env:GCP_REGION } else { "us-central1" }
$SA_NAME = "github-deploy"
$SA_EMAIL = "$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

Write-Host "=== SubsGen GCP Setup ==="
Write-Host "Project ID: $PROJECT_ID"
Write-Host "Region: $REGION"
Write-Host ""

# 1. Create project (or use existing)
gcloud projects describe $PROJECT_ID 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "[1/6] Project $PROJECT_ID already exists"
} else {
    Write-Host "[1/6] Creating project $PROJECT_ID..."
    gcloud projects create $PROJECT_ID --name=$PROJECT_NAME
}
gcloud config set project $PROJECT_ID

# 2. Enable required APIs
Write-Host "[2/6] Enabling required APIs..."
gcloud services enable run.googleapis.com artifactregistry.googleapis.com iam.googleapis.com

# 3. Create Artifact Registry repo
Write-Host "[3/6] Creating Artifact Registry repository..."
gcloud artifacts repositories create subsgen `
    --repository-format=docker `
    --location=$REGION `
    --description="SubsGen backend images" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "  (repository may already exist)" }

# 4. Create service account
Write-Host "[4/6] Creating service account $SA_EMAIL..."
gcloud iam service-accounts create $SA_NAME `
    --display-name="GitHub Actions Deploy" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "  (service account may already exist)" }

# 5. Grant roles
Write-Host "[5/6] Granting IAM roles..."
foreach ($role in @("run.admin", "artifactregistry.writer", "iam.serviceAccountUser", "storage.admin")) {
    gcloud projects add-iam-policy-binding $PROJECT_ID `
        --member="serviceAccount:$SA_EMAIL" `
        --role="roles/$role" `
        --quiet
}

# 6. Create key file
$KEY_FILE = "github-deploy-key.json"
Write-Host "[6/6] Creating key file $KEY_FILE..."
gcloud iam service-accounts keys create $KEY_FILE --iam-account=$SA_EMAIL

Write-Host ""
Write-Host "=== Setup complete ==="
Write-Host ""
Write-Host "1. Add this secret to GitHub:"
Write-Host "   Repo -> Settings -> Secrets and variables -> Actions"
Write-Host "   New repository secret: GCP_SA_KEY"
Write-Host "   Value: paste the entire contents of $KEY_FILE"
Write-Host ""
Write-Host "2. Add these repository variables (or use secrets):"
Write-Host "   GCP_PROJECT_ID = $PROJECT_ID"
Write-Host "   GCP_REGION     = $REGION"
Write-Host ""
Write-Host "3. Add GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_API_KEY_3 as GitHub secrets"
Write-Host "   (or GROQ_API_KEY) - these will be passed to Cloud Run"
Write-Host ""
Write-Host "4. Delete $KEY_FILE after adding to GitHub (do not commit it)"
Write-Host "   Remove-Item $KEY_FILE"
Write-Host ""
Write-Host "5. Push to main to trigger deploy"
Write-Host ""
