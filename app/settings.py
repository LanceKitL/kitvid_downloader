import json
import os
import shutil
import tempfile
from pathlib import Path
from threading import Lock

from . import config

SETTINGS_PATH = (
    Path(os.environ.get("VD_SETTINGS_FILE", config.BASE_DIR / "settings.json"))
    .expanduser()
    .resolve()
)

_lock = Lock()
_load_error: str | None = None


def _prepare_dir(raw: str, *, create: bool) -> Path:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Enter a download folder.")
    if len(raw) > 4096:
        raise ValueError("That folder path is too long.")
    if "\x00" in raw:
        raise ValueError("That folder path is not valid.")

    expanded = Path(os.path.expandvars(raw)).expanduser()
    if not expanded.is_absolute():
        expanded = config.BASE_DIR / expanded

    try:
        path = expanded.resolve()
    except OSError as exc:
        raise ValueError("That folder path is not valid.") from exc

    if path.exists() and not path.is_dir():
        raise ValueError("That path exists but is not a folder.")

    if create:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValueError(f"Could not create that folder: {exc}") from exc

    if path.is_dir():
        try:
            with tempfile.NamedTemporaryFile(
                dir=path, prefix=".kitvid-write-test-", delete=True
            ):
                pass
        except OSError as exc:
            raise ValueError("That folder is not writable.") from exc

    return path


def _read_settings() -> dict:
    if not SETTINGS_PATH.is_file():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read settings.json: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("settings.json must contain a JSON object.")
    return data


def _write_settings(data: dict) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_name(f"{SETTINGS_PATH.name}.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(SETTINGS_PATH)
    except OSError as exc:
        raise ValueError(f"Could not save settings: {exc}") from exc


def current() -> dict:
    return {
        "download_dir": str(config.DOWNLOAD_DIR),
        "default_download_dir": str(config.DEFAULT_DOWNLOAD_DIR),
        "file_ttl_minutes": config.FILE_TTL_MINUTES,
        "max_concurrent": config.MAX_CONCURRENT_DOWNLOADS,
        "speed_profile": config.SPEED_PROFILE,
        "speed_profiles": [
            {
                "id": key,
                "label": profile["label"],
                "description": profile["description"],
            }
            for key, profile in config.SPEED_PROFILES.items()
        ],
        "aria2_available": bool(shutil.which(config.ARIA2_BIN)),
        "settings_file": str(SETTINGS_PATH),
        "settings_error": _load_error,
    }


def load() -> dict:
    global _load_error
    _load_error = None

    with _lock:
        try:
            data = _read_settings()
        except ValueError as exc:
            _load_error = str(exc)
            data = {}

        profile = data.get("speed_profile")
        if isinstance(profile, str) and profile.strip():
            config.SPEED_PROFILE = config.normalize_speed_profile(profile)

        candidate = data.get("download_dir") if isinstance(data, dict) else None
        if isinstance(candidate, str) and candidate.strip():
            try:
                path = _prepare_dir(candidate, create=False)
            except ValueError as exc:
                _load_error = str(exc)
            else:
                if path.is_dir():
                    config.DOWNLOAD_DIR = path
                    return current()
                _load_error = f"Saved download folder is unavailable: {path}"

        config.DOWNLOAD_DIR = config.DEFAULT_DOWNLOAD_DIR
        return current()


def ensure_download_dir() -> Path:
    try:
        config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        config.DOWNLOAD_DIR = config.DEFAULT_DOWNLOAD_DIR
        config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return config.DOWNLOAD_DIR


def save_download_dir(raw: str) -> dict:
    global _load_error
    path = _prepare_dir(raw, create=True)

    with _lock:
        try:
            data = _read_settings()
        except ValueError:
            data = {}
        data["download_dir"] = str(path)
        _write_settings(data)

        config.DOWNLOAD_DIR = path
        _load_error = None
        return current()


def save_speed_profile(raw: str) -> dict:
    profile = (raw or "").strip().lower()
    if profile not in config.SPEED_PROFILES:
        raise ValueError("Choose a valid speed profile.")

    with _lock:
        try:
            data = _read_settings()
        except ValueError:
            data = {}
        data["speed_profile"] = profile
        _write_settings(data)

        config.SPEED_PROFILE = profile
        return current()
