#!/bin/zsh
set -eu
CHISE_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$CHISE_ROOT"
exec "$CHISE_ROOT/.venv/bin/python3" "$CHISE_ROOT/desktop_app.py"
