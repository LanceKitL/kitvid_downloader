#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
STAMP=".venv/.deps_hash"

# Hash of requirements.txt (works on Linux and macOS)
req_hash() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum requirements.txt | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 requirements.txt | cut -d' ' -f1
  else
    cksum requirements.txt | cut -d' ' -f1,2
  fi
}

# True only if the venv works, uses Python 3.11+, and requirements.txt is
# unchanged since the last successful install.
deps_ready() {
  [ -x ".venv/bin/python" ] || return 1
  [ -f "$STAMP" ] || return 1
  .venv/bin/python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)" >/dev/null 2>&1 || return 1
  [ "$(cat "$STAMP")" = "$(req_hash)" ] || return 1
}

if [ ! -f "requirements.txt" ]; then
  echo "requirements.txt not found in $(pwd)" >&2
  exit 1
fi

# ---------- Fast path: everything already installed, just run ----------
if deps_ready; then
  exec .venv/bin/python launcher.py
fi

echo "Some components are missing or outdated. Running setup..."

# ---------- Python (only needed if the venv must be created) ----------
if [ ! -x ".venv/bin/python" ] || ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Python 3.11+ was not found. Set PYTHON=/path/to/python3 and try again." >&2
    exit 1
  fi
  echo "Creating virtual environment..."
  rm -rf .venv
  "$PYTHON" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
fi

# ---------- Dependencies ----------
echo "Installing dependencies..."
.venv/bin/python -m pip install -r requirements.txt

# Remember that dependencies are installed for this requirements.txt
req_hash > "$STAMP"

exec .venv/bin/python launcher.py