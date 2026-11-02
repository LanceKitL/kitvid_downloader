#!/usr/bin/env bash
# Linux/macOS equivalent of start.bat
# NOTE: intentionally no "set -e": errors are handled explicitly, like the
# errorlevel checks in start.bat.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELF="$ROOT/$(basename "${BASH_SOURCE[0]}")"
cd "$ROOT" || exit 1

MARK_ACTIVE="$ROOT/.setup_active.tmp"
MARK_FFMPEG="$ROOT/.setup_ffmpeg.tmp"
MARK_VENV="$ROOT/.setup_venv.tmp"
FFMPEG_DIR="$ROOT/tools/ffmpeg"
DL_DIR="${TMPDIR:-/tmp}/kitvid-ffmpeg-dl"
DEPS_STAMP="$ROOT/.venv/.deps_hash"
PYTHON_EXE=""
BREW=""

# ---------- Detect the operating system ----------
case "$(uname -s)" in
  Darwin) OS="macos" ;;
  Linux)  OS="linux" ;;
  *)
    echo "Unsupported OS: $(uname -s). On Windows, run start.bat instead."
    exit 1
    ;;
esac

# ======================================================================
#  Helpers
# ======================================================================

# macOS: locate Homebrew (it may not be on PATH yet) and put it on PATH
find_brew() {
  BREW=""
  local b
  for b in brew /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if command -v "$b" >/dev/null 2>&1; then
      BREW="$(command -v "$b")"
      return 0
    fi
  done
  return 1
}

load_brew() {
  [ -n "$BREW" ] || return 1
  eval "$("$BREW" shellenv)"
}

# Installs Python 3.12 using the platform's package manager.
# Returns non-zero if it could not (caller then prints manual instructions).
install_python() {
  if [ "$OS" = "macos" ]; then
    find_brew || return 1
    echo "Installing Python 3.12 with Homebrew..."
    "$BREW" install python@3.12 || return 1
    load_brew
    return 0
  fi

  # Linux
  local SUDO=""
  if [ "$(id -u)" -ne 0 ]; then
    command -v sudo >/dev/null 2>&1 || return 1
    SUDO="sudo"
  fi
  echo "Installing Python 3.12 with the system package manager (may ask for your password)..."
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update
    $SUDO apt-get install -y python3.12 python3.12-venv \
      || $SUDO apt-get install -y python3 python3-venv python3-pip
  elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y python3.12 || $SUDO dnf install -y python3
  elif command -v pacman >/dev/null 2>&1; then
    $SUDO pacman -S --noconfirm python
  elif command -v zypper >/dev/null 2>&1; then
    $SUDO zypper --non-interactive install python312 || $SUDO zypper --non-interactive install python3
  else
    return 1
  fi
}

pause() {
  if [ -t 0 ]; then
    read -r -p "Press Enter to continue . . . " _ || true
  fi
}

# Hash of requirements.txt (works on Linux and macOS)
get_req_hash() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$ROOT/requirements.txt" | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$ROOT/requirements.txt" | cut -d' ' -f1
  else
    cksum "$ROOT/requirements.txt" | cut -d' ' -f1,2
  fi
}

py_in_range() {
  "$1" -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)" >/dev/null 2>&1
}

# Returns 0 only if FFmpeg, the venv, yt-dlp and all packages from the
# current requirements.txt are already in place.
quick_check() {
  # FFmpeg: system-wide or local copy
  if ! command -v ffmpeg >/dev/null 2>&1; then
    [ -x "$FFMPEG_DIR/bin/ffmpeg" ] || return 1
    PATH="$FFMPEG_DIR/bin:$PATH"
    export PATH
  fi

  [ -x ".venv/bin/python" ] || return 1
  [ -x ".venv/bin/yt-dlp" ] || return 1
  [ -f "$DEPS_STAMP" ] || return 1
  py_in_range ".venv/bin/python" || return 1

  # requirements.txt must be unchanged since the last successful install
  local req_hash stored_hash=""
  req_hash="$(get_req_hash)"
  [ -n "$req_hash" ] || return 1
  stored_hash="$(cat "$DEPS_STAMP" 2>/dev/null || true)"
  [ "$stored_hash" = "$req_hash" ] || return 1
  return 0
}

find_python() {
  PYTHON_EXE=""
  local c
  for c in "${PYTHON:-}" python3.13 python3.12 python3.11 python3 python; do
    [ -n "$c" ] || continue
    command -v "$c" >/dev/null 2>&1 || continue
    if py_in_range "$c"; then
      PYTHON_EXE="$(command -v "$c")"
      return 0
    fi
  done
  return 0
}

# ---------- Interrupted-run cleanup ----------

remove_ffmpeg() {
  rm -rf "$FFMPEG_DIR" "${FFMPEG_DIR}_tmp" >/dev/null 2>&1
  [ -e "$FFMPEG_DIR" ] && return 1
  rmdir "$ROOT/tools" >/dev/null 2>&1
  rm -f "$MARK_FFMPEG" >/dev/null 2>&1
  return 0
}

remove_venv() {
  rm -rf "$ROOT/.venv" >/dev/null 2>&1
  [ -e "$ROOT/.venv" ] && return 1
  rm -f "$MARK_VENV" >/dev/null 2>&1
  return 0
}

cleanup_partial() {
  [ -f "$MARK_FFMPEG" ] && remove_ffmpeg
  [ -f "$MARK_VENV" ] && remove_venv
  rm -rf "$DL_DIR" >/dev/null 2>&1
  [ -f "$MARK_FFMPEG" ] && return 1
  [ -f "$MARK_VENV" ] && return 1
  rm -f "$MARK_ACTIVE" >/dev/null 2>&1
  return 0
}

finish_markers() {
  rm -f "$MARK_FFMPEG" "$MARK_VENV" "$MARK_ACTIVE" >/dev/null 2>&1
  return 0
}

# Starts a hidden background watcher (once). If this terminal is closed or the
# script is killed before setup finishes, the watcher runs this script again
# with --cleanup to remove what this run created.
start_watcher() {
  [ -f "$MARK_ACTIVE" ] && return 0
  : > "$MARK_ACTIVE"
  local parent=$$
  (
    trap '' HUP
    while kill -0 "$parent" 2>/dev/null && [ -f "$MARK_ACTIVE" ]; do
      sleep 2
    done
    if [ -f "$MARK_ACTIVE" ]; then
      sleep 2
      bash "$SELF" --cleanup
    fi
  ) >/dev/null 2>&1 &
  disown 2>/dev/null || true
  return 0
}

# ---------- Error exits ----------

setup_error() {
  echo
  echo "Setup failed. Scroll up for the actual error message."
  echo "Common causes: no internet, Python version incompatible with a package, missing build tools."
  echo
  [ -f "$MARK_VENV" ] && rm -rf "$ROOT/.venv" >/dev/null 2>&1
  finish_markers
  pause
  exit 1
}

ytdlp_error() {
  echo
  echo "yt-dlp could not be started from $ROOT/.venv/bin"
  setup_error
}

ffmpeg_error() {
  echo
  echo "FFmpeg could not be installed automatically."
  echo "Install it with your package manager (e.g. 'sudo apt install ffmpeg' or 'brew install ffmpeg'),"
  echo "or place ffmpeg at:"
  echo "  $FFMPEG_DIR/bin/ffmpeg"
  echo "Then run this file again."
  echo
  pause
  exit 1
}

python_missing_error() {
  echo
  echo "Python 3.11-3.13 could not be installed automatically."
  if [ "$OS" = "macos" ]; then
    echo "Install Homebrew from https://brew.sh, then run: brew install python@3.12"
    echo "(or install Python 3.12 from https://www.python.org/downloads/)"
  else
    echo "Install Python 3.12 with your package manager (e.g. 'sudo apt install python3.12 python3.12-venv')"
  fi
  echo "or set PYTHON=/path/to/python3.12 and run this file again."
  finish_markers
  pause
  exit 1
}

# ---------- FFmpeg ----------

ffmpeg_fail() {
  cleanup_partial
  return 1
}

# Downloads every URL given into $DL_DIR as 1.zip / 2.tar.xz / ...
# Extra curl options can be passed through $CURL_EXTRA.
fetch_all() {
  local i=0 url ext
  rm -rf "$DL_DIR"
  mkdir -p "$DL_DIR" || return 1
  for url in "$@"; do
    i=$((i + 1))
    case "$url" in
      *.tar.xz) ext="tar.xz" ;;
      *)        ext="zip" ;;
    esac
    # shellcheck disable=SC2086
    curl -L --fail --progress-bar ${CURL_EXTRA:-} -o "$DL_DIR/$i.$ext" "$url" || return 1
  done
  return 0
}

ffmpeg_extract() {
  echo "Extracting FFmpeg..."
  local tmp="${FFMPEG_DIR}_tmp" f name found
  rm -rf "$tmp" >/dev/null 2>&1
  mkdir -p "$tmp" || return 1
  for f in "$DL_DIR"/*; do
    case "$f" in
      *.tar.xz) tar -xf "$f" -C "$tmp" || return 1 ;;
      *.zip)    unzip -q -o "$f" -d "$tmp" || return 1 ;;
    esac
  done
  mkdir -p "$FFMPEG_DIR/bin" || return 1
  for name in ffmpeg ffprobe; do
    found="$(find "$tmp" -type f -name "$name" | head -n 1)"
    if [ -n "$found" ]; then
      cp -f "$found" "$FFMPEG_DIR/bin/$name" || return 1
      chmod +x "$FFMPEG_DIR/bin/$name"
    fi
  done
  rm -rf "$tmp" "$DL_DIR" >/dev/null 2>&1
  [ -x "$FFMPEG_DIR/bin/ffmpeg" ] || return 1
  return 0
}

ensure_ffmpeg() {
  command -v ffmpeg >/dev/null 2>&1 && return 0
  if [ -x "$FFMPEG_DIR/bin/ffmpeg" ]; then
    PATH="$FFMPEG_DIR/bin:$PATH"; export PATH
    return 0
  fi

  echo
  echo "FFmpeg not found. Installing it before the other dependencies..."

  # macOS: Homebrew is the most reliable source (native Apple Silicon build)
  if [ "$OS" = "macos" ] && find_brew; then
    echo "Installing FFmpeg with Homebrew..."
    "$BREW" install ffmpeg
    load_brew
    command -v ffmpeg >/dev/null 2>&1 && return 0
    echo "Homebrew install failed. Trying direct download..."
  fi

  start_watcher
  : > "$MARK_FFMPEG"

  local os arch primary=() fallback=()
  os="$(uname -s)"
  arch="$(uname -m)"
  case "$os" in
    Linux)
      case "$arch" in
        x86_64|amd64)
          primary=("https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz")
          fallback=("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz")
          ;;
        aarch64|arm64)
          primary=("https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz")
          fallback=("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz")
          ;;
        *) ffmpeg_fail; return 1 ;;
      esac
      ;;
    Darwin)
      primary=("https://evermeet.cx/ffmpeg/getrelease/zip" "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip")
      ;;
    *) ffmpeg_fail; return 1 ;;
  esac

  # Primary source. Gives up if the speed stays under ~100 KB/s for 20 seconds.
  CURL_EXTRA="--connect-timeout 15 --speed-limit 102400 --speed-time 20"
  if ! fetch_all "${primary[@]}"; then
    if [ "${#fallback[@]}" -eq 0 ]; then
      ffmpeg_fail; return 1
    fi
    echo
    echo "Primary download was slow or failed. Trying the GitHub mirror..."
    CURL_EXTRA="--connect-timeout 15"
    fetch_all "${fallback[@]}" || { ffmpeg_fail; return 1; }
  fi
  CURL_EXTRA=""

  ffmpeg_extract || { ffmpeg_fail; return 1; }

  PATH="$FFMPEG_DIR/bin:$PATH"; export PATH
  return 0
}

launch() {
  trap - INT TERM HUP
  .venv/bin/python launcher.py || pause
  exit 0
}

# ======================================================================
#  --cleanup mode (run by the background watcher)
# ======================================================================
if [ "${1:-}" = "--cleanup" ]; then
  tries=0
  while true; do
    cleanup_partial && exit 0
    tries=$((tries + 1))
    [ "$tries" -ge 5 ] && exit 0
    sleep 2
  done
fi

# If this run is interrupted (Ctrl+C, terminal closed), clean up partial setup
trap 'cleanup_partial; exit 130' INT TERM HUP

# On macOS, make sure Homebrew-installed tools (python, ffmpeg) are on PATH
if [ "$OS" = "macos" ]; then
  find_brew && load_brew
fi

# ---------- Clean up after an interrupted run ----------
[ -f "$MARK_ACTIVE" ] && echo "Previous setup was interrupted. Cleaning up..."
cleanup_partial

if [ ! -f "requirements.txt" ]; then
  echo "requirements.txt not found in $ROOT"
  pause
  exit 1
fi

# ======================================================================
#  FAST PATH: if everything is already installed, skip setup entirely
# ======================================================================
if quick_check; then
  PATH="$ROOT/.venv/bin:$PATH"; export PATH
  VD_YTDLP="$ROOT/.venv/bin/yt-dlp"; export VD_YTDLP
  launch
fi

echo "Some components are missing or outdated. Running setup..."

# ---------- Step 1: FFmpeg (only installs if missing) ----------
ensure_ffmpeg || ffmpeg_error

# ---------- Step 2: Python (only needed if missing) ----------
find_python
if [ -z "$PYTHON_EXE" ]; then
  echo
  echo "Python 3.11-3.13 not found. Installing Python 3.12..."
  install_python
  find_python
  [ -n "$PYTHON_EXE" ] || python_missing_error
fi
echo "Using Python: $PYTHON_EXE"

# ---------- Step 3: Virtual environment (only created if missing/broken) ----------
make_venv() {
  start_watcher
  : > "$MARK_VENV"
  echo "Creating virtual environment..."
  "$PYTHON_EXE" -m venv .venv || setup_error
  .venv/bin/python -m pip install --upgrade pip || setup_error
}

if [ ! -x ".venv/bin/python" ]; then
  make_venv
elif ! .venv/bin/python -m pip --version >/dev/null 2>&1 || ! py_in_range ".venv/bin/python"; then
  echo "Existing virtual environment is broken or uses an unsupported Python. Recreating..."
  start_watcher
  : > "$MARK_VENV"
  rm -rf .venv
  make_venv
fi

# ---------- Step 4: Python packages and yt-dlp ----------
echo "Installing dependencies..."
.venv/bin/python -m pip install -r requirements.txt || setup_error

if [ ! -x ".venv/bin/yt-dlp" ]; then
  .venv/bin/python -m pip install -U yt-dlp || setup_error
fi

PATH="$ROOT/.venv/bin:$PATH"; export PATH
VD_YTDLP="$ROOT/.venv/bin/yt-dlp"; export VD_YTDLP

yt-dlp --version >/dev/null 2>&1 || ytdlp_error

# ---------- Remember that dependencies are installed ----------
get_req_hash > "$DEPS_STAMP"

# ---------- Setup finished: nothing to clean up anymore ----------
finish_markers
launch