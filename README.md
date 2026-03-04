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

On push to `main`, `.github/workflows/gcp-deploy.yml` deploys to the VM via SSH.

**Setup:**

1. Generate a deploy key: `ssh-keygen -t ed25519 -C "gcp-deploy" -f deploy_key -N ""`
2. Add the **public** key to the VM: `gcloud compute ssh subsgen-vm --zone=us-central1-a --command="mkdir -p ~/.ssh && echo '$(cat deploy_key.pub)' >> ~/.ssh/authorized_keys"`
3. Add GitHub Secrets (repo → Settings → Secrets and variables → Actions):
   - `GCP_SSH_KEY`: contents of `deploy_key` (private key)
   - `GCP_SSH_HOST`: `prabh@34.121.45.9` (use your VM username)
   - `GROQ_API_KEY`: your Groq API key
4. Delete `deploy_key` and `deploy_key.pub` locally after adding secrets.
