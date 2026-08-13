#!/usr/bin/env bash
# Instala servicio systemd para el bot (Linux)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="editorial-bot"
PYTHON="$(command -v python3)"

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Error: no existe $ROOT/.env — ejecuta scripts/setup.sh primero"
  exit 1
fi

if [[ -z "$PYTHON" ]]; then
  echo "Error: python3 no encontrado"
  exit 1
fi

TMP=$(mktemp)
sed -e "s|__PROJECT_DIR__|$ROOT|g" -e "s|__PYTHON__|$PYTHON|g" \
  "$ROOT/deploy/editorial-bot.service" > "$TMP"

echo "Instalando unidad systemd (requiere sudo)..."
sudo cp "$TMP" "/etc/systemd/system/${SERVICE_NAME}.service"
rm "$TMP"

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo ""
echo "Bot instalado como servicio: $SERVICE_NAME"
echo "  Estado:  sudo systemctl status $SERVICE_NAME"
echo "  Logs:    sudo journalctl -u $SERVICE_NAME -f"
echo "  Parar:   sudo systemctl stop $SERVICE_NAME"
