#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$SCRIPT_DIR/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
	if command -v python3 >/dev/null 2>&1; then
		PYTHON_BIN="$(command -v python3)"
	else
		echo "No Python interpreter found."
		exit 1
	fi
fi

"$PYTHON_BIN" -m pip install --quiet -r "$SCRIPT_DIR/spotify_requirements.txt"
"$PYTHON_BIN" "$SCRIPT_DIR/create_spotify_playlist.py"
