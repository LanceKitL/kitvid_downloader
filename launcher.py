#!/usr/bin/env python3
import os
import shutil
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))

import uvicorn

from app import config


def _port_in_use(host: str, port: int) -> bool:
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((probe_host, port)) == 0


def _open_browser(url: str, delay: float = 1.2) -> None:
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main() -> int:
    host = config.HOST
    port = config.PORT
    display_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{display_host}:{port}"

    if _port_in_use(display_host, port):
        print(f"Port {port} is already in use.")
        print(f"Opening {url} - KitVid-Downloader may already be running.")
        webbrowser.open(url)
        return 0

    print("=" * 62)
    print(f" {config.APP_NAME}")
    print("=" * 62)
    print(f" Starting at {url}")
    print(" Press Ctrl+C in this window to stop the server.")
    print("=" * 62)

    if not shutil.which("ffmpeg"):
        print(" WARNING: FFmpeg was not found on PATH.")
        print(" Merging separate video/audio streams and MP3 extraction will fail.")
        print(" Windows: winget install Gyan.FFmpeg")
        print(" Linux:   sudo apt install ffmpeg  (or your package manager)")
        print("-" * 62)

    if not shutil.which(config.YTDLP_BIN):
        print(f" WARNING: {config.YTDLP_BIN} was not found on PATH.")
        print(" Run: pip install -r requirements.txt")
        print("-" * 62)

    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    try:
        uvicorn.run("app.main:app", host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
