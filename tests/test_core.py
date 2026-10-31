import unittest
from unittest.mock import patch
from pathlib import Path

from app import config
from app.ytdlp import (
    build_download_args,
    friendly_error,
    summarize_info,
    validate_format_id,
    validate_url,
)


class ValidateUrlTests(unittest.TestCase):
    def test_accepts_http_and_https(self):
        self.assertEqual(validate_url("https://1.1.1.1/watch?v=1"), "https://1.1.1.1/watch?v=1")
        self.assertEqual(validate_url("http://1.1.1.1/a"), "http://1.1.1.1/a")

    def test_trims_whitespace(self):
        self.assertEqual(validate_url("  https://1.1.1.1/a  "), "https://1.1.1.1/a")

    def test_rejects_other_schemes(self):
        for url in ("file:///etc/passwd", "ftp://1.1.1.1/a", "javascript:alert(1)"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)

    def test_rejects_embedded_credentials(self):
        with self.assertRaises(ValueError):
            validate_url("https://user:pass@1.1.1.1/a")

    def test_rejects_private_and_metadata_addresses(self):
        for host in ("127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.10", "0.0.0.0"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                validate_url(f"http://{host}/video")

    def test_rejects_empty_and_invalid(self):
        for url in ("", "   ", "not a url", "https://"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)

    def test_private_network_can_be_allowed(self):
        original = config.ALLOW_PRIVATE_NETWORK
        config.ALLOW_PRIVATE_NETWORK = True
        try:
            self.assertEqual(validate_url("http://127.0.0.1/a"), "http://127.0.0.1/a")
        finally:
            config.ALLOW_PRIVATE_NETWORK = original


class FormatIdTests(unittest.TestCase):
    def test_accepts_normal_ids(self):
        self.assertEqual(validate_format_id("137"), "137")
        self.assertEqual(validate_format_id("best"), "best")
        self.assertEqual(validate_format_id("hls-720p"), "hls-720p")
        self.assertIsNone(validate_format_id(""))
        self.assertIsNone(validate_format_id(None))

    def test_rejects_option_injection(self):
        for value in ("-x", "--exec", "a b", "137;rm", "$(id)", "a" * 65):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_format_id(value)


class SummarizeTests(unittest.TestCase):
    def test_filters_and_sorts_formats(self):
        data = {
            "title": "Demo",
            "duration": 42.5,
            "uploader": "Someone",
            "formats": [
                {"format_id": "sb", "ext": "mhtml", "vcodec": "none", "acodec": "none"},
                {
                    "format_id": "18",
                    "ext": "mp4",
                    "height": 360,
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                    "filesize": 1024,
                },
                {
                    "format_id": "137",
                    "ext": "mp4",
                    "height": 1080,
                    "fps": 30,
                    "vcodec": "avc1",
                    "acodec": "none",
                    "filesize_approx": 2048,
                },
                {
                    "format_id": "140",
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "mp4a",
                    "abr": 128,
                },
            ],
        }
        info = summarize_info(data)

        self.assertEqual(info["title"], "Demo")
        self.assertFalse(info["drm"])
        self.assertEqual([f["format_id"] for f in info["video_formats"]], ["137", "18"])
        self.assertEqual([f["format_id"] for f in info["audio_formats"]], ["140"])
        self.assertTrue(info["video_formats"][0]["needs_audio"])

    def test_marks_drm(self):
        info = summarize_info({"title": "Locked", "formats": [{"has_drm": True}]})
        self.assertTrue(info["drm"])

    def test_estimates_sizes_from_bitrate_and_duration(self):
        data = {
            "title": "Estimated",
            "duration": 60,
            "formats": [
                {
                    "format_id": "137",
                    "ext": "mp4",
                    "height": 1080,
                    "vcodec": "avc1",
                    "acodec": "none",
                    "tbr": 1000,
                },
                {
                    "format_id": "140",
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "mp4a",
                    "abr": 128,
                },
            ],
        }
        info = summarize_info(data)
        video = info["video_formats"][0]
        audio = info["audio_formats"][0]

        audio_bytes = int(128 * 1000 / 8 * 60)
        video_bytes = int(1000 * 1000 / 8 * 60)
        self.assertEqual(audio["size_bytes"], audio_bytes)
        self.assertTrue(audio["size_is_estimate"])
        self.assertEqual(video["size_bytes"], video_bytes + audio_bytes)
        self.assertTrue(video["size_is_estimate"])
        self.assertTrue(video["filesize_label"].startswith("~"))

    def test_prefers_exact_size_and_handles_unknown(self):
        info = summarize_info(
            {
                "title": "Exact",
                "duration": 60,
                "formats": [
                    {
                        "format_id": "18",
                        "ext": "mp4",
                        "height": 360,
                        "vcodec": "avc1",
                        "acodec": "mp4a",
                        "filesize": 12345,
                    },
                    {
                        "format_id": "22",
                        "ext": "mp4",
                        "height": 720,
                        "vcodec": "avc1",
                        "acodec": "none",
                    },
                ],
            }
        )
        formats = {fmt["format_id"]: fmt for fmt in info["video_formats"]}
        exact = formats["18"]
        unknown = formats["22"]
        self.assertEqual(exact["size_bytes"], 12345)
        self.assertFalse(exact["size_is_estimate"])
        self.assertIsNone(unknown["size_bytes"])
        self.assertFalse(unknown["size_is_estimate"])


class FriendlyErrorTests(unittest.TestCase):
    def test_maps_common_errors(self):
        cases = {
            "ERROR: This video is DRM protected": "DRM-protected",
            "ERROR: Unsupported URL: https://example.com": "not supported",
            "ERROR: Private video": "private",
            "ERROR: Sign in to confirm your age": "sign-in",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertIn(expected, friendly_error(raw))

    def test_falls_back_to_last_line(self):
        message = friendly_error("WARNING: something\nERROR: Failed to connect")
        self.assertEqual(message, "Failed to connect")


class DownloadArgsTests(unittest.TestCase):
    def setUp(self):
        self.original_profile = config.SPEED_PROFILE
        self.original_aria_mode = config.ARIA2_MODE
        config.SPEED_PROFILE = "fast"
        config.ARIA2_MODE = "never"
        self.addCleanup(self._restore_config)

    def _restore_config(self):
        config.SPEED_PROFILE = self.original_profile
        config.ARIA2_MODE = self.original_aria_mode

    def test_uses_argument_array_and_best_default(self):
        args = build_download_args(
            "https://1.1.1.1/a", Path("/tmp/out"), machine_progress=False
        )
        self.assertEqual(args[args.index("-f") + 1], "bestvideo+bestaudio/best")
        self.assertEqual(args[-1], "https://1.1.1.1/a")
        self.assertIn("--no-playlist", args)

    def test_merges_audio_for_video_only_format(self):
        args = build_download_args(
            "https://1.1.1.1/a",
            Path("/tmp/out"),
            format_id="137",
            needs_audio=True,
            machine_progress=False,
        )
        self.assertIn("137+bestaudio/137", args)

    def test_audio_only_adds_mp3_extraction(self):
        args = build_download_args(
            "https://1.1.1.1/a", Path("/tmp/out"), audio_only=True, machine_progress=False
        )
        self.assertIn("-x", args)
        self.assertIn("--audio-format", args)
        self.assertIn("mp3", args)

    def test_fast_profile_uses_parallel_fragments_and_retries(self):
        args = build_download_args(
            "https://1.1.1.1/a", Path("/tmp/out"), machine_progress=False
        )

        self.assertEqual(args[args.index("--concurrent-fragments") + 1], "8")
        self.assertEqual(args[args.index("--retries") + 1], str(config.DOWNLOAD_RETRIES))
        self.assertEqual(
            args[args.index("--fragment-retries") + 1], str(config.FRAGMENT_RETRIES)
        )
        self.assertEqual(args[args.index("--throttled-rate") + 1], "100K")
        self.assertNotIn("--http-chunk-size", args)
        self.assertIn("--retry-sleep", args)

    def test_speed_profiles_change_fragment_count_and_chunking(self):
        config.SPEED_PROFILE = "balanced"
        balanced = build_download_args(
            "https://1.1.1.1/a", Path("/tmp/out"), machine_progress=False
        )
        self.assertEqual(balanced[balanced.index("--concurrent-fragments") + 1], "4")
        self.assertNotIn("--http-chunk-size", balanced)

        config.SPEED_PROFILE = "max"
        maximum = build_download_args(
            "https://1.1.1.1/a", Path("/tmp/out"), machine_progress=False
        )
        self.assertEqual(maximum[maximum.index("--concurrent-fragments") + 1], "16")
        self.assertEqual(maximum[maximum.index("--http-chunk-size") + 1], "10M")

    def test_aria2c_is_used_for_direct_http_when_available(self):
        config.ARIA2_MODE = "auto"
        config.SPEED_PROFILE = "fast"

        with patch("app.ytdlp.shutil.which", return_value="/usr/bin/aria2c"):
            args = build_download_args(
                "https://1.1.1.1/a", Path("/tmp/out"), machine_progress=False
            )

        self.assertEqual(args[args.index("--downloader") + 1], "http,https:aria2c")
        self.assertIn(
            "aria2c:-x 16 -s 16 -k 1M --file-allocation=none",
            args[args.index("--downloader-args") + 1],
        )

    def test_aria2c_can_be_disabled(self):
        config.ARIA2_MODE = "never"

        with patch("app.ytdlp.shutil.which", return_value="/usr/bin/aria2c"):
            args = build_download_args(
                "https://1.1.1.1/a", Path("/tmp/out"), machine_progress=False
            )

        self.assertNotIn("--downloader", args)


if __name__ == "__main__":
    unittest.main()
