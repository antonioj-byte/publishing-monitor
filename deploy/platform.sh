#!/usr/bin/env bash
# Helpers to pick launchd vs systemd vs manual run.

is_macos() {
  [[ "$(uname -s)" == "Darwin" ]]
}

systemd_usable() {
  if is_macos; then
    return 1
  fi
  if [[ ! -S /run/systemd/private && ! -S /var/run/systemd/private ]]; then
    return 1
  fi
  command -v systemctl >/dev/null 2>&1 || return 1
  systemctl is-system-running --quiet 2>/dev/null
}

systemd_missing_message() {
  if is_macos; then
    cat <<'EOF'
Este sistema es macOS — no usa systemd.

Usa launchd en su lugar:
  ./deploy/install-launchd.sh

O reinicia todo con:
  ./deploy/reset-and-launch-mac.sh
EOF
  else
    cat <<'EOF'
systemd no está activo en este entorno (Docker, WSL sin systemd, etc.).

Instala el servicio en un Linux con systemd, o arranca el bot a mano:
  python3 -m bot.main
EOF
  fi
}
