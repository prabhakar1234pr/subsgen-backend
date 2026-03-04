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
