import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import config, settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.default = root / "default"
        self.default.mkdir()
        self.settings_file = root / "settings.json"

        patches = [
            patch.object(config, "BASE_DIR", root),
            patch.object(config, "DEFAULT_DOWNLOAD_DIR", self.default),
            patch.object(config, "DOWNLOAD_DIR", self.default),
            patch.object(settings, "SETTINGS_PATH", self.settings_file),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        self.root = root
        self.original_profile = config.SPEED_PROFILE
        config.SPEED_PROFILE = "fast"
        self.addCleanup(self._restore_profile)

    def _restore_profile(self):
        config.SPEED_PROFILE = self.original_profile

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_creates_folder_and_persists(self):
        target = self.root / "chosen" / "nested"

        result = settings.save_download_dir(str(target))

        self.assertTrue(target.is_dir())
        self.assertEqual(result["download_dir"], str(target.resolve()))
        self.assertEqual(config.DOWNLOAD_DIR, target.resolve())
        saved = json.loads(self.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["download_dir"], str(target.resolve()))

    def test_load_restores_saved_folder(self):
        target = self.root / "chosen"
        settings.save_download_dir(str(target))
        config.DOWNLOAD_DIR = self.default

        result = settings.load()

        self.assertEqual(result["download_dir"], str(target.resolve()))
        self.assertEqual(config.DOWNLOAD_DIR, target.resolve())
        self.assertIsNone(result["settings_error"])

    def test_load_falls_back_when_saved_folder_is_missing(self):
        missing = self.root / "gone"
        self.settings_file.write_text(
            json.dumps({"download_dir": str(missing)}), encoding="utf-8"
        )

        result = settings.load()

        self.assertEqual(result["download_dir"], str(self.default.resolve()))
        self.assertIn("unavailable", result["settings_error"])

    def test_rejects_path_that_is_a_file(self):
        file_path = self.root / "not-a-folder"
        file_path.write_text("x", encoding="utf-8")

        with self.assertRaises(ValueError):
            settings.save_download_dir(str(file_path))

    def test_rejects_empty_path(self):
        with self.assertRaises(ValueError):
            settings.save_download_dir("   ")

    def test_relative_path_resolves_against_project(self):
        result = settings.save_download_dir("clips")

        self.assertEqual(result["download_dir"], str((self.root / "clips").resolve()))

    def test_speed_profile_is_saved_and_exposed(self):
        result = settings.save_speed_profile("max")

        self.assertEqual(result["speed_profile"], "max")
        self.assertEqual(config.SPEED_PROFILE, "max")
        saved = json.loads(self.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["speed_profile"], "max")
        self.assertEqual(
            [profile["id"] for profile in result["speed_profiles"]],
            ["balanced", "fast", "max"],
        )

    def test_speed_profile_rejects_unknown_values(self):
        with self.assertRaises(ValueError):
            settings.save_speed_profile("ludicrous")

    def test_saving_download_dir_preserves_speed_profile(self):
        settings.save_speed_profile("balanced")
        settings.save_download_dir(str(self.root / "clips"))

        saved = json.loads(self.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["speed_profile"], "balanced")
        self.assertEqual(saved["download_dir"], str((self.root / "clips").resolve()))

    def test_load_restores_speed_profile(self):
        self.settings_file.write_text(
            json.dumps({"speed_profile": "max"}), encoding="utf-8"
        )
        config.SPEED_PROFILE = "fast"

        result = settings.load()

        self.assertEqual(result["speed_profile"], "max")
        self.assertEqual(config.SPEED_PROFILE, "max")


if __name__ == "__main__":
    unittest.main()
