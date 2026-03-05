import logging
import os
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from routers import video
from routers import reel_pipeline
from utils.ffmpeg_check import check_ffmpeg_available

# ── Logging config: timestamped, env-controlled level ────────────────────────
LOG_LEVEL = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("subsgen")

# Reduce noise from third-party libs (crewai, httpx, etc.)
for name in ("httpx", "httpcore", "urllib3", "openai"):
    logging.getLogger(name).setLevel(logging.WARNING)

app = FastAPI(
    title="Instagram Subtitles API",
    description="AI-powered reel pipeline: LLaVA clip analysis + Llama edit planning + Pixabay music + FFmpeg editing",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming request and response."""
    start = time.perf_counter()
    method = request.method
    path = request.url.path
    client = request.client.host if request.client else "unknown"
    logger.info(f"[REQ] {method} {path} | client={client}")
    try:
        response = await call_next(request)
        elapsed = (time.perf_counter() - start) * 1000
        logger.info(f"[RES] {method} {path} | status={response.status_code} | {elapsed:.0f}ms")
        return response
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        logger.error(f"[ERR] {method} {path} | {type(e).__name__}: {e} | {elapsed:.0f}ms")
        raise


@app.on_event("startup")
async def startup():
    logger.info("=" * 60)
    logger.info("SubsGen API starting")
    ffmpeg_ok, ffmpeg_msg = check_ffmpeg_available()
    if not ffmpeg_ok:
        logger.warning(f"[STARTUP] {ffmpeg_msg}")
    else:
        logger.info("[STARTUP] FFmpeg OK")
    logger.info("=" * 60)


app.include_router(video.router, prefix="/api", tags=["subtitles"])
app.include_router(reel_pipeline.router, prefix="/api", tags=["reel-pipeline"])
logger.info("Routers registered: /api (video, reel-pipeline)")


@app.get("/")
async def root():
    logger.debug("GET /")
    return {
        "message": "Instagram Subtitles API",
        "status": "running",
        "version": "0.3.0",
        "ai_pipeline": "LLaVA (Groq) + Llama-3.3-70b (Groq) + Pixabay Music + FFmpeg"
    }


@app.get("/api/health")
async def health_check():
    logger.debug("GET /api/health")
    ffmpeg_ok, ffmpeg_msg = check_ffmpeg_available()
    return {
        "status": "healthy",
        "ffmpeg": "ok" if ffmpeg_ok else "missing",
        "ffmpeg_detail": ffmpeg_msg if not ffmpeg_ok else None,
    }
