#!/usr/bin/env bash
# Setup inicial del bot editorial Telegram
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Bot editorial — setup en $ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Creado .env — edítalo con tus claves antes de clasificar o arrancar el bot."
else
  echo ".env ya existe"
fi

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif command -v python3 >/dev/null; then
  echo "Instalando dependencias con pip..."
  python3 -m pip install -r requirements.txt --user -q 2>/dev/null || \
    python3 -m pip install -r requirements.txt -q
else
  echo "Error: python3 no encontrado"
  exit 1
fi

python3 scripts/init_db.py
python3 scripts/load_medios.py
python3 scripts/test_paywall_feeds.py

echo ""
echo "==> Setup base completado"
echo ""
echo "Próximos pasos:"
echo "  1. Edita .env con ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN"
echo "  2. Envía /start a tu bot → python scripts/get_telegram_chat_id.py"
echo "  3. python scripts/run_ingest_once.py"
echo "  4. python scripts/classify_pending.py   (o reclassify_all.py --yes)"
echo "  5. python scripts/print_report.py       (vista previa)"
echo "  6. python -m bot.main                   (arrancar bot)"
echo ""
echo "Arranque automático:"
echo "  Linux:  ./deploy/install-systemd.sh"
echo "  macOS:  ./deploy/install-launchd.sh"
