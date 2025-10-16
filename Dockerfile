FROM python:3.13.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 file \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m appuser && \
    mkdir -p /app/media/original /app/media/thumbnails /app/data && \
    chown -R appuser:appuser /app

USER appuser
EXPOSE 8000

ENV APP_MODULE=backend.app.main:app \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000

CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host ${UVICORN_HOST} --port ${UVICORN_PORT} --workers ${UVICORN_WORKERS:-1}"]
