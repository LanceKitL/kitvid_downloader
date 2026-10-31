import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_DOWNLOAD_DIR = (
    Path(os.environ.get("VD_DOWNLOAD_DIR", BASE_DIR / "downloads")).expanduser().resolve()
)
DOWNLOAD_DIR = DEFAULT_DOWNLOAD_DIR

FILE_TTL_MINUTES = int(os.environ.get("VD_FILE_TTL_MINUTES", "60"))
MAX_CONCURRENT_DOWNLOADS = max(1, int(os.environ.get("VD_MAX_CONCURRENT", "2")))
DOWNLOAD_TIMEOUT_SECONDS = int(os.environ.get("VD_DOWNLOAD_TIMEOUT", "3600"))
INFO_TIMEOUT_SECONDS = int(os.environ.get("VD_INFO_TIMEOUT", "60"))
DOWNLOAD_RETRIES = max(1, int(os.environ.get("VD_DOWNLOAD_RETRIES", "10")))
FRAGMENT_RETRIES = max(1, int(os.environ.get("VD_FRAGMENT_RETRIES", "10")))
RETRY_SLEEP = os.environ.get("VD_RETRY_SLEEP", "exp=1:20").strip()

DEFAULT_SPEED_PROFILE = "fast"

SPEED_PROFILES = {
    "balanced": {
        "label": "Balanced",
        "description": "4 parallel fragments. Gentler on servers and slower connections.",
        "fragments": 4,
        "http_chunk_size": "",
        "throttled_rate": "500K",
        "aria2_connections": 8,
    },
    "fast": {
        "label": "Fast",
        "description": "16 parallel fragments. The best default for most connections.",
        "fragments": 16,
        "http_chunk_size": "10M",
        "throttled_rate": "1M",
        "aria2_connections": 16,
    },
    "max": {
        "label": "Max",
        "description": "32 parallel fragments plus chunked HTTP. Fastest, but some sites may throttle or rate-limit it.",
        "fragments": 32,
        "http_chunk_size": "10M",
        "throttled_rate": "2M",
        "aria2_connections": 32,
    },
}

def normalize_speed_profile(value: str | None) -> str:
    key = (value or "").strip().lower()
    return key if key in SPEED_PROFILES else DEFAULT_SPEED_PROFILE


_requested_profile = os.environ.get("VD_SPEED_PROFILE", DEFAULT_SPEED_PROFILE).strip().lower()
SPEED_PROFILE = _requested_profile if _requested_profile in SPEED_PROFILES else DEFAULT_SPEED_PROFILE

ARIA2_BIN = os.environ.get("VD_ARIA2", "aria2c")
# auto: use aria2c when it is on PATH; never: always use yt-dlp's native downloader
ARIA2_MODE = os.environ.get("VD_ARIA2_MODE", "auto").strip().lower()

ALLOW_PRIVATE_NETWORK = os.environ.get("VD_ALLOW_PRIVATE_NETWORK", "0") == "1"

MAX_FILESIZE = os.environ.get("VD_MAX_FILESIZE", "").strip()

HOST = os.environ.get("VD_HOST", "127.0.0.1")
PORT = int(os.environ.get("VD_PORT", "8000"))

YTDLP_BIN = os.environ.get("VD_YTDLP", "yt-dlp")

APP_NAME = "KitVid-Downloader"
