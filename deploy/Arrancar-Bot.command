#!/usr/bin/env bash
# Doble clic en Finder para instalar y arrancar el bot (macOS).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Bot editorial Telegram ==="
echo "Carpeta: $ROOT"
echo ""

if [[ ! -f "$ROOT/.env" ]]; then
  echo "No existe .env — copiando plantilla..."
  cp .env.example .env
  echo ""
  echo "Abre .env con TextEdit y rellena:"
  echo "  TELEGRAM_BOT_TOKEN"
  echo "  TELEGRAM_CHAT_ID"
  echo ""
  open -e "$ROOT/.env"
  read -r -p "Pulsa Enter cuando hayas guardado .env..."
fi

echo "→ Instalando servicio en segundo plano..."
"$ROOT/deploy/install-launchd.sh"

echo ""
echo "→ Estado:"
python3 "$ROOT/scripts/bot_status.py"

echo ""
echo "Prueba en Telegram: /ping"
read -r -p "Pulsa Enter para cerrar..."
