FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data \
    && python3 scripts/prewarm_embeddings.py || true

ENV PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/data/editorial.db \
    TIMEZONE=Europe/Madrid

ENTRYPOINT ["/app/deploy/docker-entrypoint.sh"]
CMD ["python3", "-m", "bot.main"]
