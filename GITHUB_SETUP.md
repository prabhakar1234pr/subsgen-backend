# GitHub setup for Cloud Run deploy

GCP is ready. Add these in GitHub:

## 1. Secrets (Settings → Secrets and variables → Actions)

| Secret | Value |
|--------|-------|
| **GCP_SA_KEY** | Entire contents of `backend/github-deploy-key.json` |
| **GROQ_API_KEY_1** | Your Groq API key |
| **GROQ_API_KEY_2** | (optional) Second key |
| **GROQ_API_KEY_3** | (optional) Third key |
| **GROQ_API_KEY** | (optional) Single key if not using 1/2/3 |

## 2. Variables (optional — defaults are set)

| Variable | Value |
|----------|-------|
| **GCP_PROJECT_ID** | `subsgen-run-p554` |
| **GCP_REGION** | `us-central1` |
| **GCS_BUCKET** | `subsgen-reels-subsgen-run-p554` (auto-created on first deploy) |

**Note:** For GCS signed URLs, the Cloud Run default SA needs `roles/iam.serviceAccountTokenCreator` on itself. Run once:
```bash
PROJ_NUM=$(gcloud projects describe subsgen-run-p554 --format='value(projectNumber)')
gcloud iam service-accounts add-iam-policy-binding ${PROJ_NUM}-compute@developer.gserviceaccount.com \
  --member="serviceAccount:${PROJ_NUM}-compute@developer.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --project=subsgen-run-p554
```

The deploy SA needs `roles/storage.admin` to create the GCS bucket. If you set up GCP before this, run:
```bash
gcloud projects add-iam-policy-binding subsgen-run-p554 \
  --member="serviceAccount:github-deploy@subsgen-run-p554.iam.gserviceaccount.com" \
  --role="roles/storage.admin"
```

## 3. Push to main

```bash
git add .
git commit -m "Cloud Run deploy"
git push origin main
```

## 4. Get your backend URL

After deploy succeeds:
- [Cloud Console](https://console.cloud.google.com/run?project=subsgen-run-p554) → subsgen-api → URL
- Or: `gcloud run services describe subsgen-api --region=us-central1 --format='value(status.url)'`

## 5. Update frontend

In Vercel: set `BACKEND_URL` = your Cloud Run URL.
