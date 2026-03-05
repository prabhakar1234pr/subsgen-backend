FROM python:3.11-slim

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl fonts-dejavu-core fontconfig \
    && rm -rf /var/lib/apt/lists/* && fc-cache -f -v
RUN mkdir -p /home/user/app && chown -R user:user /home/user/app

USER user
RUN pip install --user uv

COPY --chown=user pyproject.toml .
RUN uv venv /home/user/app/.venv
ENV PATH="/home/user/app/.venv/bin:$PATH"

RUN uv pip install --python /home/user/app/.venv/bin/python \
    fastapi "uvicorn[standard]" python-multipart \
    groq httpx python-dotenv \
    crewai langchain-groq

COPY --chown=user . .
RUN mkdir -p /home/user/app/assets/music

EXPOSE 8080
ENV PORT=8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

CMD ["sh", "-c", "exec python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
