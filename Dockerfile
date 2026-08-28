# ---------- Build stage ----------
FROM python:3.12-slim AS builder

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/deps -r requirements.txt

# ---------- Runtime stage ----------
FROM python:3.12-slim AS runtime

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/data/hf_cache

# ffmpeg нужен для конвертации аудио (imageio-ffmpeg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /deps /usr/local
COPY . /app

RUN mkdir -p /data && chmod -R 777 /data

EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=30s \
    CMD python -c "import sqlite3, os; sqlite3.connect(os.environ.get('DATABASE_PATH', '/data/english_bot.db')).execute('SELECT 1')" || exit 1

CMD ["python", "-m", "bot.main"]