# SubsGen on Google Cloud Run

Cloud Run supports **60-minute request timeout** (vs Render's 15–30s), so the full pipeline can complete.

## Prerequisites

- [Google Cloud SDK (gcloud)](https://cloud.google.com/sdk/docs/install) installed
- Logged in: `gcloud auth login`
- Billing enabled on your GCP account (Cloud Run requires it; free tier includes monthly credits)

## 1. Run setup script

From the `backend` directory:

**PowerShell (Windows):**
```powershell
cd backend
.\scripts\setup-gcp.ps1
```

**Bash (Linux/Mac):**
```bash
cd backend
bash scripts/setup-gcp.sh
```

This creates:

- A new GCP project (or uses existing)
- Artifact Registry for Docker images
- Service account `github-deploy` with deploy permissions
- Key file `github-deploy-key.json`

**Important:** GCP project IDs are globally unique. If `subsgen-backend` is taken or you get a permission error, use a unique ID:

**PowerShell:**
```powershell
$env:GCP_PROJECT_ID = "subsgen-backend-488200"   # or subsgen-YOURNAME, etc.
.\scripts\setup-gcp.ps1
```

**Bash:**
```bash
export GCP_PROJECT_ID=subsgen-backend-488200
bash scripts/setup-gcp.sh
```

**Optional:** Customize region:
```powershell
$env:GCP_REGION = "us-east1"
```

## 2. Add GitHub secrets

1. Go to **GitHub** → **prabhakar1234pr/subsgen-backend** → **Settings** → **Secrets and variables** → **Actions**
2. Create these **secrets**:

   | Secret        | Value                                      |
   |---------------|--------------------------------------------|
   | `GCP_SA_KEY`  | Entire contents of `github-deploy-key.json` |
   | `GROQ_API_KEY_1` | Your Groq API key                        |
   | `GROQ_API_KEY_2` | (optional) Second key for rotation       |
   | `GROQ_API_KEY_3` | (optional) Third key for rotation       |
   | `GROQ_API_KEY`   | (optional) Single key if not using 1/2/3  |

3. Add **variables** (optional; defaults work):

   | Variable       | Value          |
   |----------------|----------------|
   | `GCP_PROJECT_ID` | Your project ID |
   | `GCP_REGION`     | `us-central1` |

4. Delete the key file locally:

   ```bash
   rm github-deploy-key.json
   ```

## 3. Deploy

Push to `main`:

```bash
git add .
git commit -m "Add Cloud Run deploy"
git push origin main
```

GitHub Actions will build and deploy the backend to Cloud Run.

## 4. Get your backend URL

After deploy, your API URL will look like:

```
https://subsgen-api-XXXXX-uc.a.run.app
```

Find it in:

- [Cloud Console](https://console.cloud.google.com/run) → your service → URL
- Or: `gcloud run services describe subsgen-api --region=us-central1 --format='value(status.url)'`

## 5. Update frontend

In **Vercel** (or wherever the frontend is deployed):

- Set `BACKEND_URL` = `https://subsgen-api-XXXXX-uc.a.run.app`
- Redeploy the frontend

## Cloud Run specs (sufficient, not overboard)

| Setting | Value |
|---------|-------|
| Memory | 2 GiB |
| CPU | 2 vCPU |
| Timeout | 60 min |
| Min instances | 0 (scale to zero) |
| Max instances | 2 |

## Cost

- Cloud Run free tier: 2M requests/month, 360K vCPU-seconds, 180K GiB-seconds
- With credits, typical usage is low or free for moderate traffic
