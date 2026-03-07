#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/APP/pi_cli.py" ]]; then
  exec python3 "$SCRIPT_DIR/APP/pi_cli.py" "$@"
fi
exec python3 "$SCRIPT_DIR/pi_cli.py" "$@"
