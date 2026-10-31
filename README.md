# KitVid-Downloader

A personal, local web front end for `yt-dlp` and `FFmpeg`. Add one or many videos to a queue, pick a format for each, watch live progress and estimated size, and save the results. Everything runs on your machine, from your IP, into a folder you choose.

Use it only for content you own or are otherwise allowed to save (for example Creative Commons, public domain, or a site's permitted offline use). Respect copyright and each site's terms of service. DRM-protected streams are not supported.

## Features

- Multi-video queue: add as many URLs as you like, each with its own format and audio choice.
- Download all, download individually, cancel, or delete jobs.
- Live progress with downloaded/total size in MB/GB, speed, and ETA.
- Size estimates before downloading (based on bitrate × duration when the site does not report a size).
- Editable download location with a native folder chooser, persisted in `settings.json`.
- Automatic TTL cleanup of finished files.
- One-click launchers for Windows, Linux, and macOS.

## Requirements

- Python 3.11+
- `yt-dlp` (installed by `requirements.txt`)
- `ffmpeg` on `PATH` (needed for merging separate video/audio streams and MP3 extraction)

```bash
# Windows
winget install Gyan.FFmpeg

# Fedora
sudo dnf install ffmpeg

# Debian / Ubuntu
sudo apt install ffmpeg
```

## Quick start

### Windows

Install Python 3.11+ (enable "Add Python to PATH") and FFmpeg, then double-click:

```text
start.bat
```

The script creates `.venv` if needed, installs dependencies, starts the server, and opens <http://127.0.0.1:8000> in your browser. Keep the console window open; close it or press `Ctrl+C` to stop.

### Linux / macOS

```bash
./start.sh
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python launcher.py
```

`launcher.py` opens the browser for you. If you prefer no auto-open, run `python -m app.main`.

## Web interface

1. Set the download location at the top. Click **Browse...** to pick a folder with your system's folder chooser, or type/paste a path. Changes apply to new downloads; jobs already running keep their original folder.
2. Paste a URL and click **Add video**. The app fetches metadata and adds a card to the queue.
3. Choose a format and optionally **Audio only (MP3)** for that card. The estimated size updates.
4. Repeat for more videos, then click **Download all** (or **Download** on a single card).
5. Watch progress in the Downloads panel. Finished jobs expose **Save file**; use **Cancel** or **Delete** as needed.

## Settings

The download location is stored in `settings.json` at the project root (gitignored) and loaded at startup. If that location is unavailable or not writable, the app falls back to the default and explains the problem in the UI.

The **Browse...** button opens a chooser on the machine running the server. On Linux it uses `zenity` or `kdialog` (with a Tk fallback), on macOS it uses the native dialog, and on Windows it uses the PowerShell folder browser (with a Tk fallback). Because the app is local-only, the dialog appears on your desktop.

Precedence: `settings.json` → `VD_DOWNLOAD_DIR` → `./downloads`.

Environment variables (all optional):

| Variable | Default | Meaning |
| --- | --- | --- |
| `VD_DOWNLOAD_DIR` | `./downloads` | Initial download folder when no saved setting exists. |
| `VD_SETTINGS_FILE` | `./settings.json` | Alternate settings file path (useful for tests). |
| `VD_FILE_TTL_MINUTES` | `60` | Delete finished/errored job files after this many minutes. `0` disables cleanup. |
| `VD_MAX_CONCURRENT` | `2` | Maximum simultaneous yt-dlp processes; extra queue items wait. |
| `VD_DOWNLOAD_TIMEOUT` | `3600` | Per-job timeout in seconds. |
| `VD_INFO_TIMEOUT` | `60` | Metadata lookup timeout in seconds. |
| `VD_MAX_FILESIZE` | unset | Passed to `yt-dlp --max-filesize`, e.g. `2G`. |
| `VD_ALLOW_PRIVATE_NETWORK` | `0` | Set to `1` to allow URLs that resolve to private/loopback addresses. |
| `VD_HOST` / `VD_PORT` | `127.0.0.1` / `8000` | Bind address. Keep it on loopback. |
| `VD_YTDLP` | `yt-dlp` | Path to the yt-dlp binary. |
| `VD_FOLDER_PICKER_FAKE` | unset | Test hook: return this folder (or `cancel`) instead of opening a chooser. |

## CLI

```bash
python cli.py info "https://example.com/video"
python cli.py download "https://example.com/video" -f 137 --needs-audio
python cli.py download "https://example.com/video" --audio -o ~/Music
```

`info` prints normalized JSON metadata and formats. `download` shows yt-dlp's normal progress output. The CLI writes directly to `--output` and does not use the saved web setting.

## API

All endpoints return JSON unless noted. There is no authentication and no CORS: intended for `localhost` only.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness check. |
| `GET` | `/api/settings` | Current download folder, default, TTL, concurrency. |
| `PUT` | `/api/settings` | `{"download_dir": "..."}`; validates, creates, and saves the folder. |
| `POST` | `/api/settings/browse` | `{"initial_dir": "..."}` → opens the native folder chooser; returns `{"cancelled", "download_dir"}`. |
| `POST` | `/api/info` | `{"url": "..."}` → title, thumbnail, duration, formats, estimated sizes, DRM flag. |
| `GET` | `/api/jobs` | `{"jobs": [...], "active": n}`; newest first. |
| `POST` | `/api/jobs` | `{"url", "format_id", "audio_only", "needs_audio", "title"}` → job. |
| `GET` | `/api/jobs/{id}` | Job status, progress, bytes, speed, ETA, error, download URL. |
| `GET` | `/api/jobs/{id}/file` | Serves the finished file. |
| `DELETE` | `/api/jobs/{id}` | Cancels a running/queued job, or deletes a finished one. |

Format objects include `size_bytes`, `size_is_estimate`, and `filesize_label` (prefixed with `~` for estimates). Video-only formats include the best audio stream in their estimated total when a duration is known. Jobs expose `downloaded_bytes`, `total_bytes`, `total_bytes_is_estimate`, and `output_dir`.

When `format_id` is omitted, yt-dlp uses `bestvideo+bestaudio/best`. Set `needs_audio: true` for video-only formats so the worker merges in the best audio stream.

## Security model

This is a local tool, not a hardened public service. Implemented protections:

- Binds to `127.0.0.1` by default.
- Rejects non-HTTP(S) URLs, embedded credentials, oversized URLs, and hosts resolving to private, loopback, link-local, or metadata addresses (best-effort SSRF guard; yt-dlp follows redirects without re-checking).
- Rejects unsafe format ids so input cannot become a command-line option.
- Passes arguments as arrays, never through a shell.
- Requires same-origin browser requests for state-changing methods and sends no CORS headers.
- The folder chooser is a local GUI process; the selected path is only accepted after the normal settings validation.
- Each job writes to its own subdirectory under the configured folder; file serving is restricted to that job's folder.
- Does not attempt to bypass DRM; DRM content is rejected with a clear message.

Do not expose this server to the internet or a shared network without authentication, rate limiting, per-user quotas, and stronger egress controls.

## Limitations

- DRM-protected streams (Netflix, Disney+, most paid services) are unsupported.
- Sites change their players constantly; update yt-dlp deliberately and re-run the tests.
- Some sites block datacenter/VPN IPs or require sign-in cookies. There is no cookie UI yet.
- Playlists are disabled (`--no-playlist`); each URL resolves to one video.
- Size estimates are approximate, especially for HLS/live streams or unknown-duration videos.
- Jobs live in memory and are lost when the server restarts; finished files on disk remain until you delete them.
- Finished files are served without HTTP Range support.
- Changing the download folder does not move existing files.

## Tests

```bash
python -m unittest discover -s tests -v
```

UI tests use Playwright separately; they are not part of the unit test suite. Set `VD_FOLDER_PICKER_FAKE` to a folder (or `cancel`) to exercise the Browse flow without a GUI dialog.
