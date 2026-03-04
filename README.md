# SubsGen API

FastAPI backend for generating Instagram-style viral subtitles on talking head videos.

## Features

- **Subtitles only**: faster-whisper (local) or Groq Whisper → word-by-word ASS → FFmpeg burn
- **AI Reel Pipeline**: 4-agent pipeline (Whisper v3, Llama 4 Scout VLM, Llama 3.3 70B Brain, Music Supervisor) → trim, 9:16, concat, music mix, subtitles
- Music from Internet Archive (CC0) or bundled fallback

## API Endpoints

- `GET /` - API info
- `GET /api/health` - Health check
- `GET /api/reel-pipeline/status` - Groq keys status
- `POST /api/process` - Single video → subtitled MP4
- `POST /api/process-reel` - Multiple videos → ZIP of subtitled MP4s
- `POST /api/reel-pipeline` - Raw clips → AI reel (MP4 + caption header)

## Local Setup

```bash
cp .env.example .env
# Add GROQ_API_KEY (or GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_API_KEY_3) to .env

uv sync
uv run uvicorn main:app --reload --port 7860
```

## Deploy to Fly.io

1. Install [Fly CLI](https://fly.io/docs/hands-on/install-flyctl/)
2. Sign up: `fly auth signup` (or `fly auth login`)
3. Launch: `fly launch` (from backend directory)
4. Set secrets: `fly secrets set GROQ_API_KEY=your_key`
5. Deploy: `fly deploy`

API will be at `https://subsgen-api.fly.dev` (or your chosen app name).

## Deploy to Google Cloud (e2-micro Always Free)

**Project:** `subsgen-backend-488200` | **VM:** `subsgen-vm` | **IP:** `34.121.45.9`

1. SSH: `gcloud compute ssh subsgen-vm --zone=us-central1-a`
2. Add your Groq key: `nano ~/subsgen/.env` → change `REPLACE_WITH_YOUR_KEY` to your key
3. Build & run: `cd ~/subsgen && sudo docker build -t subsgen-api . && sudo docker run -d --name subsgen --restart unless-stopped -p 7860:7860 --env-file .env subsgen-api`
4. API: `http://34.121.45.9:7860`

### CI/CD (GitHub Actions → GCP VM)

On push to `main`, `.github/workflows/gcp-deploy.yml` deploys via `gcloud compute ssh`.

**Setup:**

1. Create a GCP service account with **Compute Instance Admin (v1)** role:
   ```bash
   gcloud iam service-accounts create github-deploy --display-name="GitHub Deploy"
   gcloud projects add-iam-policy-binding subsgen-backend-488200 \
     --member="serviceAccount:github-deploy@subsgen-backend-488200.iam.gserviceaccount.com" \
     --role="roles/compute.instanceAdmin.v1"
   ```

2. Create and download a JSON key:
   ```bash
   gcloud iam service-accounts keys create key.json \
     --iam-account=github-deploy@subsgen-backend-488200.iam.gserviceaccount.com
   ```

3. Add GitHub Secrets (repo → Settings → Secrets and variables → Actions):
   - `GCP_SA_KEY`: paste the entire contents of `key.json`
   - `GROQ_API_KEY`: your Groq API key

4. Delete `key.json` after adding the secret.
