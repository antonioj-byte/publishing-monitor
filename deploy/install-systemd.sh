#!/usr/bin/env bash
# Instala servicio systemd para el bot (Linux)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="editorial-bot"
PYTHON="$(command -v python3)"
if [[ -x "$ROOT/.venv/bin/python3" ]]; then
  PYTHON="$ROOT/.venv/bin/python3"
fi

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Error: no existe $ROOT/.env — ejecuta scripts/setup.sh primero"
  exit 1
fi

if [[ -z "$PYTHON" ]]; then
  echo "Error: python3 no encontrado"
  exit 1
fi

install_unit() {
  local src="$1"
  local dest="$2"
  local tmp
  tmp="$(mktemp)"
  sed -e "s|__PROJECT_DIR__|$ROOT|g" -e "s|__PYTHON__|$PYTHON|g" \
    "$src" > "$tmp"
  sudo cp "$tmp" "$dest"
  rm "$tmp"
}

echo "Instalando unidades systemd (requiere sudo)..."
install_unit "$ROOT/deploy/editorial-bot.service" "/etc/systemd/system/${SERVICE_NAME}.service"
install_unit "$ROOT/deploy/editorial-bot-watchdog.service" "/etc/systemd/system/editorial-bot-watchdog.service"
install_unit "$ROOT/deploy/editorial-bot-watchdog.timer" "/etc/systemd/system/editorial-bot-watchdog.timer"

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME" editorial-bot-watchdog.timer
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl start editorial-bot-watchdog.timer

echo ""
echo "Bot instalado como servicio: $SERVICE_NAME"
echo "Watchdog timer: editorial-bot-watchdog.timer (cada 2 min)"
echo "  Estado:  sudo systemctl status $SERVICE_NAME"
echo "  Logs:    sudo journalctl -u $SERVICE_NAME -f"
echo "  Diag:    python3 scripts/bot_status.py"
