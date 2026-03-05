# Create GCS bucket for SubsGen reel outputs
# Lifecycle: delete objects after 24h (free tier friendly)
# Run once: .\scripts\setup-gcs-bucket.ps1

$ErrorActionPreference = "Stop"
$PROJECT_ID = if ($env:GCP_PROJECT_ID) { $env:GCP_PROJECT_ID } else { "subsgen-run-p554" }
$REGION = if ($env:GCP_REGION) { $env:GCP_REGION } else { "us-central1" }
$BUCKET = "subsgen-reels-$PROJECT_ID"

Write-Host "=== SubsGen GCS Bucket Setup ==="
Write-Host "Project: $PROJECT_ID | Bucket: $BUCKET"
gcloud config set project $PROJECT_ID

# Enable Storage API
gcloud services enable storage.googleapis.com --quiet

# Create bucket (ignore if exists)
gcloud storage buckets create "gs://$BUCKET" --location=$REGION 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "Bucket may already exist" }

# Lifecycle: delete after 1 day (24h)
$LIFECYCLE = @'
{"lifecycle":{"rule":[{"action":{"type":"Delete"},"condition":{"age":1}}]}}
'@
$tmp = Join-Path $env:TEMP "subsgen-lifecycle.json"
$LIFECYCLE | Out-File -FilePath $tmp -Encoding utf8 -NoNewline
gcloud storage buckets update "gs://$BUCKET" --lifecycle-file=$tmp
Remove-Item $tmp -ErrorAction SilentlyContinue

# Grant Cloud Run default SA access
$PROJECT_NUM = (gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
$SA = "$PROJECT_NUM-compute@developer.gserviceaccount.com"
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" `
  --member="serviceAccount:$SA" `
  --role="roles/storage.objectAdmin" `
  --quiet

Write-Host ""
Write-Host "=== Done ==="
Write-Host "Add to Cloud Run env: GCS_BUCKET=$BUCKET"
Write-Host "  (GitHub vars or: gcloud run services update subsgen-api --set-env-vars GCS_BUCKET=$BUCKET)"
