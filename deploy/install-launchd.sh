#!/usr/bin/env bash
# Instala LaunchAgents del bot y del watchdog (macOS)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.editorial-bot"
WATCHDOG_LABEL="com.editorial-bot.watchdog"
PLIST_DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"
WATCHDOG_PLIST_DEST="$HOME/Library/LaunchAgents/${WATCHDOG_LABEL}.plist"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "Este script es para macOS. En Linux usa deploy/install-systemd.sh"
  exit 1
fi

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Error: no existe $ROOT/.env — ejecuta scripts/setup.sh primero"
  exit 1
fi

PYTHON="$(command -v python3)"
if [[ -x "$ROOT/.venv/bin/python3" ]]; then
  PYTHON="$ROOT/.venv/bin/python3"
fi
if [[ -z "$PYTHON" ]]; then
  echo "Error: python3 no encontrado"
  exit 1
fi

mkdir -p "$ROOT/data" "$HOME/Library/LaunchAgents"

WRAPPER="$ROOT/deploy/run-bot.sh"
cat > "$WRAPPER" << EOF
#!/usr/bin/env bash
set -euo pipefail
set -a
source "$ROOT/.env"
set +a
cd "$ROOT"
echo "\$(date -Is) run-bot.sh starting pid=\$\$" >> "$ROOT/data/bot.log"
exec "$PYTHON" -m bot.main
EOF
chmod +x "$WRAPPER"

sed -e "s|__PROJECT_DIR__|$ROOT|g" -e "s|__PYTHON__|$WRAPPER|g" \
  "$ROOT/deploy/com.editorial-bot.plist" > "$PLIST_DEST"

/usr/libexec/PlistBuddy -c "Delete :ProgramArguments" "$PLIST_DEST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :ProgramArguments array" "$PLIST_DEST"
/usr/libexec/PlistBuddy -c "Add :ProgramArguments:0 string $WRAPPER" "$PLIST_DEST"

sed -e "s|__PROJECT_DIR__|$ROOT|g" -e "s|__PYTHON__|$PYTHON|g" \
  "$ROOT/deploy/com.editorial-bot.watchdog.plist" > "$WATCHDOG_PLIST_DEST"

UID_NUM="$(id -u)"
launchctl bootout "gui/$UID_NUM/$WATCHDOG_LABEL" 2>/dev/null || true
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
pkill -f "python.*bot.main" 2>/dev/null || true
pkill -f "deploy/run-bot.sh" 2>/dev/null || true
sleep 1

launchctl bootstrap "gui/$UID_NUM" "$PLIST_DEST"
launchctl enable "gui/$UID_NUM/$LABEL"
launchctl bootstrap "gui/$UID_NUM" "$WATCHDOG_PLIST_DEST"
launchctl enable "gui/$UID_NUM/$WATCHDOG_LABEL"

echo ""
echo "Bot instalado:"
echo "  Servicio:   $LABEL"
echo "  Watchdog:   $WATCHDOG_LABEL (cada 2 min)"
echo "  Logs bot:   $ROOT/data/bot.log"
echo "  Errores:    $ROOT/data/bot.error.log"
echo "  Watchdog:   $ROOT/data/watchdog.log"
echo ""
echo "Estado: python3 scripts/bot_status.py"
echo "Reinicio: launchctl kickstart -k gui/$UID_NUM/$LABEL"
