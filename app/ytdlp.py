import ipaddress
import json
import re
import shlex
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from . import config

FORMAT_ID_RE = re.compile(r"^[A-Za-z0-9_.+-]{1,64}$")


class YtdlpError(Exception):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


def validate_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Enter a video URL.")
    if len(raw) > 2048:
        raise ValueError("That URL is too long.")
    if any(ch.isspace() for ch in raw):
        raise ValueError("That URL contains whitespace.")

    parts = urlparse(raw)
    if parts.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are supported.")
    if not parts.hostname:
        raise ValueError("That URL is missing a hostname.")
    if parts.username or parts.password:
        raise ValueError("URLs with embedded credentials are not supported.")

    if not config.ALLOW_PRIVATE_NETWORK:
        _reject_internal_host(parts.hostname)

    return raw


def _reject_internal_host(hostname: str) -> None:
    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError("Could not resolve that hostname.") from exc

    for entry in addresses:
        ip = ipaddress.ip_address(entry[4][0].split("%", 1)[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(
                "That host resolves to a private or internal address, which is blocked."
            )


def validate_format_id(format_id: str | None) -> str | None:
    if format_id is None:
        return None
    format_id = format_id.strip()
    if not format_id:
        return None
    if not FORMAT_ID_RE.match(format_id) or format_id.startswith("-"):
        raise ValueError("Invalid format selection.")
    return format_id


def _display_size(num: float | None) -> str:
    if not num:
        return ""
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return ""


def _num(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _estimate_bytes(bitrate_kbps: float | None, duration: float | None) -> int | None:
    if not bitrate_kbps or not duration or duration <= 0:
        return None
    return int(bitrate_kbps * 1000 / 8 * duration)


def summarize_info(data: dict) -> dict:
    raw_formats = data.get("formats") or ([data] if data.get("url") else [])
    drm = bool(data.get("_has_drm")) or any(f.get("has_drm") for f in raw_formats)
    duration = _num(data.get("duration"))

    formats = []
    for fmt in raw_formats:
        if fmt.get("has_drm"):
            continue
        ext = fmt.get("ext")
        if not ext or ext in ("mhtml", "none"):
            continue
        vcodec_raw = fmt.get("vcodec")
        acodec_raw = fmt.get("acodec")
        vcodec = vcodec_raw or "none"
        acodec = acodec_raw or "none"
        if vcodec_raw is None and acodec_raw is None:
            vcodec = "unknown"
            acodec = "unknown"
        if vcodec == "none" and acodec == "none":
            continue

        height = fmt.get("height") if isinstance(fmt.get("height"), int) else None
        width = fmt.get("width") if isinstance(fmt.get("width"), int) else None
        kind = "audio" if vcodec == "none" else "video"

        exact_size = _num(fmt.get("filesize")) or _num(fmt.get("filesize_approx"))
        if exact_size:
            own_size = int(exact_size)
            own_is_estimate = False
        else:
            bitrate = (
                _num(fmt.get("abr"))
                if kind == "audio"
                else _num(fmt.get("vbr")) or _num(fmt.get("tbr"))
            )
            own_size = _estimate_bytes(bitrate, duration)
            own_is_estimate = own_size is not None

        formats.append(
            {
                "format_id": fmt.get("format_id"),
                "ext": ext,
                "kind": kind,
                "height": height,
                "width": width,
                "fps": _num(fmt.get("fps")),
                "vcodec": vcodec,
                "acodec": acodec,
                "tbr": _num(fmt.get("tbr")),
                "abr": _num(fmt.get("abr")),
                "note": fmt.get("format_note") or "",
                "protocol": fmt.get("protocol") or "",
                "needs_audio": vcodec != "none" and acodec == "none",
                "_own_size": own_size,
                "_own_is_estimate": own_is_estimate,
            }
        )

    video = [f for f in formats if f["kind"] == "video"]
    audio = [f for f in formats if f["kind"] == "audio"]
    video.sort(key=lambda f: (f["height"] or 0, f["tbr"] or 0), reverse=True)
    audio.sort(key=lambda f: (f["abr"] or 0, f["tbr"] or 0), reverse=True)

    best_audio_size = audio[0]["_own_size"] if audio else None
    best_audio_is_estimate = audio[0]["_own_is_estimate"] if audio else False

    for fmt in formats:
        size = fmt.pop("_own_size")
        is_estimate = fmt.pop("_own_is_estimate")

        if fmt["needs_audio"] and best_audio_size:
            size = (size or 0) + best_audio_size
            is_estimate = is_estimate or best_audio_is_estimate

        fmt["size_bytes"] = size
        fmt["size_is_estimate"] = bool(size is not None and is_estimate)
        fmt["filesize"] = size
        fmt["filesize_label"] = (
            ("~" if fmt["size_is_estimate"] else "") + _display_size(size)
        )

    return {
        "title": data.get("title") or "Untitled",
        "thumbnail": data.get("thumbnail"),
        "duration": duration,
        "uploader": data.get("uploader") or data.get("channel"),
        "webpage_url": data.get("webpage_url") or data.get("original_url"),
        "extractor": data.get("extractor_key") or data.get("extractor"),
        "is_live": bool(data.get("is_live")),
        "drm": drm,
        "formats": video + audio,
        "video_formats": video,
        "audio_formats": audio[:25],
    }


def friendly_error(stderr: str) -> str:
    text = (stderr or "").strip()
    lowered = text.lower()

    if "drm" in lowered:
        return "This content is DRM-protected and cannot be downloaded."
    if "unsupported url" in lowered or "no suitable extractor" in lowered:
        return "This site is not supported by yt-dlp."
    if "private video" in lowered:
        return "This video is private."
    if any(token in lowered for token in ("sign in", "log in", "login", "cookies")):
        return "This content requires sign-in, and no cookies were provided."
    if "403" in lowered or "forbidden" in lowered:
        return "The site refused the download (HTTP 403). It may be blocking this IP or require cookies."
    if "geo" in lowered or "country" in lowered:
        return "This video is geo-restricted in your region."
    if "unavailable" in lowered or "not available" in lowered:
        return "This video is unavailable."
    if "timed out" in lowered or "timeout" in lowered:
        return "The request timed out."

    lines = [line for line in text.splitlines() if line.strip()]
    last = lines[-1] if lines else "yt-dlp reported an unknown error."
    last = re.sub(r"^ERROR:\s*", "", last)
    return last[:300]


def fetch_info(url: str) -> dict:
    args = [
        config.YTDLP_BIN,
        "--dump-single-json",
        "--no-playlist",
        "--no-warnings",
        "--socket-timeout",
        "30",
        url,
    ]
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=config.INFO_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise YtdlpError(
            "yt-dlp is not installed or not on PATH.",
            f"Tried to run: {config.YTDLP_BIN}",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise YtdlpError("Fetching video information timed out.") from exc

    if proc.returncode != 0:
        raise YtdlpError(friendly_error(proc.stderr), proc.stderr.strip()[-2000:])

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise YtdlpError("Could not read video information from yt-dlp.") from exc

    return summarize_info(data)


def aria2_path() -> str | None:
    if config.ARIA2_MODE in ("0", "false", "never", "off"):
        return None
    return shutil.which(config.ARIA2_BIN)


def build_download_args(
    url: str,
    out_dir: Path,
    format_id: str | None = None,
    audio_only: bool = False,
    needs_audio: bool = False,
    *,
    machine_progress: bool = True,
) -> list[str]:
    profile_key = config.normalize_speed_profile(config.SPEED_PROFILE)
    profile = config.SPEED_PROFILES[profile_key]

    args = [
        config.YTDLP_BIN,
        "--no-playlist",
        "--newline",
        "--no-color",
        "--no-warnings",
        "--socket-timeout",
        "30",
        "--retries",
        str(config.DOWNLOAD_RETRIES),
        "--fragment-retries",
        str(config.FRAGMENT_RETRIES),
        "--concurrent-fragments",
        str(profile["fragments"]),
        "--continue",
        "-P",
        str(out_dir),
        "-o",
        "%(title).150B [%(id)s].%(ext)s",
    ]

    if config.RETRY_SLEEP:
        args += ["--retry-sleep", config.RETRY_SLEEP]

    if profile["throttled_rate"]:
        args += ["--throttled-rate", profile["throttled_rate"]]

    if profile["http_chunk_size"]:
        args += ["--http-chunk-size", profile["http_chunk_size"]]

    if machine_progress:
        args += [
            "--progress",
            "--progress-template",
            "download:PROGRESS:%(progress.status)s:%(progress.downloaded_bytes)s"
            ":%(progress.total_bytes)s:%(progress.total_bytes_estimate)s"
            ":%(progress.speed)s:%(progress.eta)s",
        ]

    if audio_only:
        args += [
            "-f",
            "bestaudio/best",
            "-x",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
        ]
    else:
        if format_id:
            selected = f"{format_id}+bestaudio/{format_id}" if needs_audio else format_id
        else:
            selected = "bestvideo+bestaudio/best"
        args += ["-f", selected]

    if config.MAX_FILESIZE:
        args += ["--max-filesize", config.MAX_FILESIZE]

    downloader = aria2_path()
    if downloader:
        args += [
            "--downloader",
            "http,https:aria2c",
            "--downloader-args",
            "aria2c:-x {n} -s {n} -k 1M --file-allocation=none".format(
                n=profile["aria2_connections"]
            ),
        ]

    args.append(url)
    return args


def printable_command(args: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in args)
