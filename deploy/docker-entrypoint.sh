#!/usr/bin/env bash
# First-boot setup for cloud containers (Railway, Fly.io, VPS).
set -euo pipefail

cd /app
mkdir -p /app/data

echo "→ Inicializando esquema SQLite (idempotente)..."
python3 -c "from db.connection import init_schema; init_schema()"

echo "→ Sincronizando medios.csv con la base de datos..."
python3 scripts/load_medios.py
python3 scripts/sync_tiers.py

exec "$@"
