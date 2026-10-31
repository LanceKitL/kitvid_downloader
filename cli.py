#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path

from app.ytdlp import (
    YtdlpError,
    build_download_args,
    fetch_info,
    printable_command,
    validate_url,
)


def cmd_info(args: argparse.Namespace) -> int:
    try:
        info = fetch_info(validate_url(args.url))
    except (ValueError, YtdlpError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    try:
        url = validate_url(args.url)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.format and args.format.startswith("-"):
        print("error: invalid format selection.", file=sys.stderr)
        return 1

    out_dir = Path(args.output).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    command = build_download_args(
        url,
        out_dir,
        format_id=args.format,
        audio_only=args.audio,
        needs_audio=args.needs_audio,
        machine_progress=False,
    )

    print(f"Saving to {out_dir}", file=sys.stderr)
    print(f"Running: {printable_command(command)}", file=sys.stderr)

    try:
        return subprocess.call(command)
    except FileNotFoundError:
        print("error: yt-dlp is not installed or not on PATH.", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video-downloader",
        description="Thin personal-use wrapper around yt-dlp.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    info_parser = subparsers.add_parser("info", help="Show video metadata and formats.")
    info_parser.add_argument("url")
    info_parser.set_defaults(func=cmd_info)

    download_parser = subparsers.add_parser("download", help="Download a video or audio stream.")
    download_parser.add_argument("url")
    download_parser.add_argument("-f", "--format", help="yt-dlp format id, e.g. 137")
    download_parser.add_argument(
        "--needs-audio",
        action="store_true",
        help="Merge the selected video-only format with the best audio stream.",
    )
    download_parser.add_argument(
        "-a", "--audio", action="store_true", help="Extract audio as MP3."
    )
    download_parser.add_argument(
        "-o", "--output", default="downloads", help="Output directory (default: downloads)."
    )
    download_parser.set_defaults(func=cmd_download)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
