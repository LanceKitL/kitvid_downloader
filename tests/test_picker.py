import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import folder_picker


class FolderPickerFakeTests(unittest.TestCase):
    def test_fake_returns_resolved_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "chosen"
            target.mkdir()

            with patch.dict(
                os.environ, {"VD_FOLDER_PICKER_FAKE": str(target)}, clear=False
            ):
                selected = folder_picker.pick_folder()

            self.assertEqual(selected, str(target.resolve()))

    def test_fake_supports_cancellation(self):
        for value in ("cancel", "CANCEL", "none", ""):
            with self.subTest(value=value), patch.dict(
                os.environ, {"VD_FOLDER_PICKER_FAKE": value}, clear=False
            ):
                self.assertIsNone(folder_picker.pick_folder())

    def test_initial_dir_falls_back_to_parent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing"
            self.assertEqual(
                folder_picker._initial_dir(str(missing)), str(Path(temp_dir))
            )


if __name__ == "__main__":
    unittest.main()
