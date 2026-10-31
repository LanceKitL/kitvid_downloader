#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python 3.11+ was not found. Set PYTHON=/path/to/python3 and try again." >&2
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating virtual environment..."
  "$PYTHON" -m venv .venv
  echo "Installing dependencies..."
  .venv/bin/python -m pip install --upgrade pip
fi

echo "Checking dependencies..."
.venv/bin/python -m pip install -q -r requirements.txt

exec .venv/bin/python launcher.py
