#!/usr/bin/env bash
# Alias macOS → script unificado de reset
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/reset-and-launch.sh" "$@"
