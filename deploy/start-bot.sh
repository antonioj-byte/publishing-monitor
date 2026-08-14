#!/usr/bin/env bash
# Arranca el bot cargando .env desde la raíz del proyecto (no depende del cwd).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Error: no existe $ROOT/.env"
  echo "  cp .env.example .env"
  echo "  Rellena TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID"
  exit 1
fi

PYTHON="$(command -v python3)"
if [[ -x "$ROOT/.venv/bin/python3" ]]; then
  PYTHON="$ROOT/.venv/bin/python3"
fi

set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a

mkdir -p "$ROOT/data"
echo "$(date -Is) start-bot.sh pid=$$" >> "$ROOT/data/bot.log"
exec "$PYTHON" -m bot.main
