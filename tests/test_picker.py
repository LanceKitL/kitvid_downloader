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


class WindowsPickerTests(unittest.TestCase):
    def test_encodes_script_as_utf16_base64(self):
        import base64

        encoded = folder_picker._encode_powershell("Write-Output 'ok'")
        self.assertEqual(
            base64.b64decode(encoded).decode("utf-16-le"), "Write-Output 'ok'"
        )

    def test_returns_selected_folder_from_result_file(self):
        selected = "C:\\Users\\José\\Vidéos"

        def fake_run(args, env=None):
            self.assertIn("-EncodedCommand", args)
            self.assertIn("-STA", args)
            with open(env["KITVID_PICKER_RESULT"], "w", encoding="utf-8") as handle:
                handle.write(selected)
            return 0, "", ""

        with patch.object(
            folder_picker.shutil, "which", return_value="powershell.exe"
        ), patch.object(folder_picker, "_run", side_effect=fake_run), patch.object(
            folder_picker, "_pick_tk"
        ) as tk:
            self.assertEqual(folder_picker._pick_windows("C:\\Users"), selected)
            tk.assert_not_called()

    def test_cancel_returns_none_without_tk_fallback(self):
        with patch.object(
            folder_picker.shutil, "which", return_value="powershell.exe"
        ), patch.object(folder_picker, "_run", return_value=(2, "", "")), patch.object(
            folder_picker, "_pick_tk"
        ) as tk:
            self.assertIsNone(folder_picker._pick_windows(None))
            tk.assert_not_called()

    def test_powershell_failure_falls_back_to_tk(self):
        with patch.object(
            folder_picker.shutil, "which", return_value="powershell.exe"
        ), patch.object(
            folder_picker, "_run", return_value=(3, "", "boom")
        ), patch.object(
            folder_picker, "_pick_tk", return_value=(True, "/picked")
        ) as tk:
            self.assertEqual(folder_picker._pick_windows(None), "/picked")
            tk.assert_called_once()

    def test_missing_result_file_falls_back_to_tk(self):
        with patch.object(
            folder_picker.shutil, "which", return_value="powershell.exe"
        ), patch.object(folder_picker, "_run", return_value=(0, "", "")), patch.object(
            folder_picker, "_pick_tk", return_value=(True, "/picked")
        ) as tk:
            self.assertEqual(folder_picker._pick_windows(None), "/picked")
            tk.assert_called_once()

    def test_reports_underlying_error_when_everything_fails(self):
        with patch.object(
            folder_picker.shutil, "which", return_value="powershell.exe"
        ), patch.object(
            folder_picker, "_run", return_value=(3, "", "boom")
        ), patch.object(
            folder_picker, "_pick_tk", return_value=(False, None)
        ):
            with self.assertRaises(folder_picker.FolderPickerUnavailable) as ctx:
                folder_picker._pick_windows(None)
            self.assertIn("boom", str(ctx.exception))

    def test_missing_powershell_uses_tk(self):
        with patch.object(
            folder_picker.shutil, "which", return_value=None
        ), patch.object(folder_picker, "_pick_tk", return_value=(True, "/picked")):
            self.assertEqual(folder_picker._pick_windows(None), "/picked")


if __name__ == "__main__":
    unittest.main()
