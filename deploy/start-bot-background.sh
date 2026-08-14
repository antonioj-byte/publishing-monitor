#!/usr/bin/env bash
# Arranca el bot en segundo plano (cloud / Linux / prueba manual).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pkill -f "python.*bot.main" 2>/dev/null || true
sleep 1

mkdir -p "$ROOT/data"
nohup "$ROOT/deploy/start-bot.sh" >> "$ROOT/data/bot.log" 2>&1 &
echo "Bot arrancado (pid $!). Logs: tail -f $ROOT/data/bot.log"
sleep 2
python3 "$ROOT/scripts/bot_status.py" || true
