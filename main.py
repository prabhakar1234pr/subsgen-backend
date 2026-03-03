from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from routers import video
from routers import reel_pipeline

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

app.include_router(video.router, prefix="/api", tags=["subtitles"])
app.include_router(reel_pipeline.router, prefix="/api", tags=["reel-pipeline"])


@app.get("/")
async def root():
    return {
        "message": "Instagram Subtitles API",
        "status": "running",
        "version": "0.3.0",
        "ai_pipeline": "LLaVA (Groq) + Llama-3.3-70b (Groq) + Pixabay Music + FFmpeg"
    }


@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}
