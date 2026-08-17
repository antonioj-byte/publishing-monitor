#!/usr/bin/env bash
# First-boot setup for cloud containers (Railway, Fly.io, VPS).
set -euo pipefail

cd /app
mkdir -p /app/data

if [[ ! -f /app/data/editorial.db ]]; then
  echo "→ Primera arrancada: inicializando base de datos..."
  python3 scripts/init_db.py
  echo "→ Base de datos lista. La ingesta arranca con el scheduler del bot."
fi

echo "→ Sincronizando medios.csv con la base de datos..."
python3 scripts/load_medios.py
python3 scripts/sync_tiers.py

exec "$@"
