# Backend Tests

End-to-end tests for all 5 agents and the full ReelFlow pipeline.

## Setup

```bash
pip install -e ".[dev]"
# or
pip install pytest pytest-asyncio
```

## Run

```bash
pytest tests/ -v
```

## Mock Setup

All external dependencies are mocked in `conftest.py`:

| Dependency | Mock |
|------------|------|
| **Groq API** | Mock client returns sample transcript, analysis, holistic review, edit plan, music refine/pick |
| **key_manager** | `has_keys=True`, `next_key="test-groq-key-12345"` |
| **subprocess** | ffprobe returns duration; ffmpeg creates minimal output files |
| **httpx** | Internet Archive search/metadata/download return sample data |

No real API keys or network calls are made.

## Test Files

| File | Coverage |
|------|----------|
| `test_transcriber.py` | Transcriber (Whisper) |
| `test_video_analyst.py` | VideoAnalyst (VLM) |
| `test_holistic_reviewer.py` | HolisticReviewer |
| `test_brain.py` | EditDirector (Brain) |
| `test_music_supervisor.py` | MusicSupervisor |
| `test_subtitle_verifier.py` | SubtitleVerifier |
| `test_reel_flow_e2e.py` | Full pipeline (all 6 agents) |
