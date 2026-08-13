#!/usr/bin/env bash
# Instala LaunchAgent para el bot (macOS)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.editorial-bot"
PLIST_DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "Este script es para macOS. En Linux usa deploy/install-systemd.sh"
  exit 1
fi

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Error: no existe $ROOT/.env — ejecuta scripts/setup.sh primero"
  exit 1
fi

PYTHON="$(command -v python3)"
if [[ -z "$PYTHON" ]]; then
  echo "Error: python3 no encontrado"
  exit 1
fi

mkdir -p "$ROOT/data" "$HOME/Library/LaunchAgents"

# launchd no carga .env automáticamente; exportamos variables al plist vía wrapper
WRAPPER="$ROOT/deploy/run-bot.sh"
cat > "$WRAPPER" << EOF
#!/usr/bin/env bash
set -a
source "$ROOT/.env"
set +a
cd "$ROOT"
exec "$PYTHON" -m bot.main
EOF
chmod +x "$WRAPPER"

sed -e "s|__PROJECT_DIR__|$ROOT|g" -e "s|__PYTHON__|$WRAPPER|g" \
  "$ROOT/deploy/com.editorial-bot.plist" > "$PLIST_DEST"

# Reemplazar ProgramArguments para usar wrapper
/usr/libexec/PlistBuddy -c "Delete :ProgramArguments" "$PLIST_DEST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :ProgramArguments array" "$PLIST_DEST"
/usr/libexec/PlistBuddy -c "Add :ProgramArguments:0 string $WRAPPER" "$PLIST_DEST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"
launchctl enable "gui/$(id -u)/$LABEL"

echo ""
echo "Bot instalado como LaunchAgent: $LABEL"
echo "  Logs: $ROOT/data/bot.log"
echo "  Parar: launchctl bootout gui/$(id -u)/$LABEL"
