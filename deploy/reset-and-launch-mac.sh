#!/usr/bin/env bash
# Resetea y relanza el bot en macOS con el código más reciente.
# Uso:
#   ./deploy/reset-and-launch-mac.sh
#   ./deploy/reset-and-launch-mac.sh --reclassify   # también reclasifica artículos (lento)
#   ./deploy/reset-and-launch-mac.sh --no-pull      # si ya hiciste git pull
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LABEL="com.editorial-bot"
DO_PULL=1
DO_RECLASSIFY=0

for arg in "$@"; do
  case "$arg" in
    --no-pull) DO_PULL=0 ;;
    --reclassify) DO_RECLASSIFY=1 ;;
    -h|--help)
      echo "Uso: $0 [--reclassify] [--no-pull]"
      exit 0
      ;;
    *)
      echo "Opción desconocida: $arg"
      exit 1
      ;;
  esac
done

if [[ "$(uname)" != "Darwin" ]]; then
  echo "Este script es solo para macOS."
  echo "En Linux: git pull && pip install -r requirements.txt && python3 scripts/sync_tiers.py && sudo systemctl restart editorial-bot"
  exit 1
fi

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Error: no existe .env — ejecuta primero: cp .env.example .env"
  echo "Rellena ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID."
  exit 1
fi

echo "==> Reset bot editorial (macOS) en $ROOT"
echo ""

if [[ "$DO_PULL" -eq 1 ]]; then
  echo "→ git pull"
  git pull origin main
fi

echo "→ Dependencias Python"
if [[ -d "$ROOT/.venv" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi
python3 -m pip install -r requirements.txt -q

echo "→ Base de datos, medios y tiers"
python3 scripts/init_db.py
python3 scripts/sync_tiers.py

echo "→ Precalentar modelo de embeddings"
python3 scripts/prewarm_embeddings.py

if [[ "$DO_RECLASSIFY" -eq 1 ]]; then
  echo "→ Reclasificar artículos (puede tardar; usa API Anthropic)"
  python3 scripts/reclassify_all.py --yes
else
  echo "→ (Omitido reclassify; añade --reclassify si quieres reaplicar criterios)"
fi

echo "→ Parar instancias anteriores del bot"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
pkill -f "python.*bot.main" 2>/dev/null || true
pkill -f "deploy/run-bot.sh" 2>/dev/null || true
sleep 1

echo "→ Instalar / reiniciar LaunchAgent"
"$ROOT/deploy/install-launchd.sh"

echo "→ Arrancar bot"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

sleep 2
echo ""
echo "==> Bot relanzado"
echo "  Logs:      tail -f $ROOT/data/bot.log"
echo "  Errores:   tail -f $ROOT/data/bot.error.log"
echo "  Estado:    launchctl print gui/$(id -u)/$LABEL"
echo "  Probar:    python3 scripts/print_report.py"
echo "  Telegram:  /informe"
echo ""

if [[ -f "$ROOT/data/bot.log" ]]; then
  echo "Últimas líneas del log:"
  tail -n 8 "$ROOT/data/bot.log" || true
fi
