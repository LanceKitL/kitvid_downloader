import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import config, folder_picker, settings
from app.jobs import manager
from app.main import app


class ApiTests(unittest.TestCase):
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
            patch.object(config, "SPEED_PROFILE", "fast"),
            patch.object(config, "ARIA2_MODE", "never"),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        manager.jobs.clear()
        self.root = root
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_settings_round_trip(self):
        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["download_dir"], str(self.default.resolve()))

        target = self.root / "chosen"
        response = self.client.put(
            "/api/settings", json={"download_dir": str(target)}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["download_dir"], str(target.resolve()))
        self.assertTrue(target.is_dir())

    def test_settings_rejects_file_path(self):
        file_path = self.root / "file.txt"
        file_path.write_text("x", encoding="utf-8")

        response = self.client.put(
            "/api/settings", json={"download_dir": str(file_path)}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("not a folder", response.json()["detail"])

    def test_speed_profile_round_trip(self):
        response = self.client.put("/api/settings/speed", json={"profile": "max"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["speed_profile"], "max")

        current = self.client.get("/api/settings").json()
        self.assertEqual(current["speed_profile"], "max")
        self.assertEqual(
            [profile["id"] for profile in current["speed_profiles"]],
            ["balanced", "fast", "max"],
        )
        saved = json.loads(self.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["speed_profile"], "max")

    def test_speed_profile_rejects_unknown_values(self):
        response = self.client.put("/api/settings/speed", json={"profile": "warp"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("valid speed profile", response.json()["detail"])

    def test_browse_returns_selected_folder(self):
        target = self.root / "picked"
        target.mkdir()

        with patch.object(folder_picker, "pick_folder", return_value=str(target)):
            response = self.client.post(
                "/api/settings/browse", json={"initial_dir": str(self.default)}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"cancelled": False, "download_dir": str(target)},
        )

    def test_browse_reports_cancellation(self):
        with patch.object(folder_picker, "pick_folder", return_value=None):
            response = self.client.post(
                "/api/settings/browse", json={"initial_dir": str(self.default)}
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["cancelled"])

    def test_browse_reports_unavailable_picker(self):
        with patch.object(
            folder_picker,
            "pick_folder",
            side_effect=folder_picker.FolderPickerUnavailable("no picker available"),
        ):
            response = self.client.post("/api/settings/browse", json={})

        self.assertEqual(response.status_code, 501)
        self.assertIn("no picker available", response.json()["detail"])

    def test_jobs_list_is_empty(self):
        response = self.client.get("/api/jobs")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"jobs": [], "active": 0})

    def test_rejects_cross_origin_writes(self):
        response = self.client.put(
            "/api/settings",
            json={"download_dir": str(self.root / "other")},
            headers={"Origin": "https://evil.example"},
        )

        self.assertEqual(response.status_code, 403)

    def test_index_is_branded(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("KitVid-Downloader", response.text)


if __name__ == "__main__":
    unittest.main()
