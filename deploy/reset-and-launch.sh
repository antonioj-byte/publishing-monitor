#!/usr/bin/env bash
# Reset completo y relanzamiento del bot editorial.
#
# Uso:
#   ./deploy/reset-and-launch.sh --full          # BD nueva + ingest + classify + bot
#   ./deploy/reset-and-launch.sh --fresh-db      # solo borra y recrea la BD
#   ./deploy/reset-and-launch.sh                 # mantiene BD, actualiza código y reinicia
#   ./deploy/reset-and-launch.sh --no-pull       # sin git pull
#
# macOS: usa launchd. Linux: systemd si está instalado, si no ejecuta bot en foreground hint.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LABEL="com.editorial-bot"
SERVICE_NAME="editorial-bot"
DO_PULL=1
DO_FRESH_DB=0
DO_INGEST=0
DO_CLASSIFY=0
DO_VERIFY=1

for arg in "$@"; do
  case "$arg" in
    --no-pull) DO_PULL=0 ;;
    --fresh-db) DO_FRESH_DB=1 ;;
    --ingest) DO_INGEST=1 ;;
    --classify) DO_CLASSIFY=1 ;;
    --full)
      DO_FRESH_DB=1
      DO_INGEST=1
      DO_CLASSIFY=1
      ;;
    --no-verify) DO_VERIFY=0 ;;
    -h|--help)
      cat <<'EOF'
Uso: ./deploy/reset-and-launch.sh [opciones]

  --full         Borra BD, reingiere, clasifica, verifica agentes y relanza bot
  --fresh-db     Borra data/editorial.db y recrea esquema vacío
  --ingest       Ejecuta una pasada de ingestión
  --classify     Clasifica artículos pendientes (API Anthropic o modo offline)
  --no-pull      No hace git pull
  --no-verify    Omite verify_filter_agent.py al final

Ejemplo desde cero:
  ./deploy/reset-and-launch.sh --full
EOF
      exit 0
      ;;
    *)
      echo "Opción desconocida: $arg (usa --help)"
      exit 1
      ;;
  esac
done

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Error: no existe .env"
  echo "  cp .env.example .env"
  echo "  Rellena ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"
  exit 1
fi

echo "==> Reset bot editorial en $ROOT"
echo ""

if [[ "$DO_PULL" -eq 1 ]]; then
  echo "→ git pull"
  git pull origin main || git pull
fi

echo "→ Dependencias Python"
if [[ -d "$ROOT/.venv" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi
python3 -m pip install -r requirements.txt -q

if [[ "$DO_FRESH_DB" -eq 1 ]]; then
  echo "→ Borrar y recrear base de datos"
  python3 scripts/reset_db.py
fi

echo "→ Medios y tiers"
python3 scripts/init_db.py
python3 scripts/load_medios.py
python3 scripts/sync_tiers.py

echo "→ Precalentar embeddings"
python3 scripts/prewarm_embeddings.py

if [[ "$DO_INGEST" -eq 1 ]]; then
  echo "→ Ingesta (puede tardar 1-3 min)"
  python3 scripts/run_ingest_once.py
fi

if [[ "$DO_CLASSIFY" -eq 1 ]]; then
  echo "→ Clasificación de artículos pendientes"
  python3 - <<'PY'
from ai.classify import classify_all_pending
stats = classify_all_pending()
print(f"Clasificados: {stats['classified']}, fallidos: {stats['failed']}, pendientes: {stats['remaining']}")
PY
fi

if [[ "$DO_VERIFY" -eq 1 ]]; then
  echo "→ Diagnóstico pipeline"
  python3 scripts/diagnose_pipeline.py
  echo ""
  echo "→ Verificación agentes (filtro + priorización)"
  python3 scripts/verify_filter_agent.py || true
fi

stop_bot() {
  if [[ "$(uname)" == "Darwin" ]]; then
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  elif command -v systemctl >/dev/null 2>&1; then
    sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  fi
  pkill -f "python.*bot.main" 2>/dev/null || true
  pkill -f "deploy/run-bot.sh" 2>/dev/null || true
}

start_bot() {
  if [[ "$(uname)" == "Darwin" ]]; then
    "$ROOT/deploy/install-launchd.sh"
    launchctl kickstart -k "gui/$(id -u)/$LABEL"
    echo ""
    echo "Bot relanzado (launchd: $LABEL)"
    echo "  Logs:    tail -f $ROOT/data/bot.log"
    echo "  Errores: tail -f $ROOT/data/bot.error.log"
  elif command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q "$SERVICE_NAME"; then
    sudo systemctl restart "$SERVICE_NAME"
    echo ""
    echo "Bot relanzado (systemd: $SERVICE_NAME)"
    echo "  Logs: sudo journalctl -u $SERVICE_NAME -f"
  else
    echo ""
    echo "Servicio no instalado. Arranca manualmente:"
    echo "  python3 -m bot.main"
    echo "O instala:"
    echo "  Linux: ./deploy/install-systemd.sh"
    echo "  macOS: ./deploy/install-launchd.sh"
    return
  fi

  sleep 2
  python3 scripts/bot_status.py || true
  if [[ -f "$ROOT/data/bot.log" ]]; then
    echo ""
    echo "Últimas líneas del log:"
    tail -n 8 "$ROOT/data/bot.log" || true
  fi
}

echo "→ Parar instancias anteriores"
stop_bot
sleep 1

echo "→ Arrancar bot"
start_bot

echo ""
echo "==> Listo"
echo "  Probar informe:  python3 scripts/print_report.py 7 estados unidos"
echo "  Telegram:        /informe 7 estados unidos"
echo "  Verificar filtro: python3 scripts/verify_filter_agent.py"
