---
title: Instagram Subtitles API
emoji: 🎬
colorFrom: purple
colorTo: pink
sdk: docker
app_port: 7860
---

# Instagram Subtitles API

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

## Secrets (Space Settings)

Add `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3` (or `GROQ_API_KEY`) as Secrets for full AI pipeline.

