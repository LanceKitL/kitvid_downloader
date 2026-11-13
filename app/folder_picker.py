import base64
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TITLE = "Choose a download folder"
DIALOG_TIMEOUT_SECONDS = 600

WINDOWS_PICKER_SCRIPT = r"""
$ErrorActionPreference = 'Stop'

function Write-PickerFile([string]$Path, [string]$Value) {
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Value, $utf8)
}

$owner = $null
$dialog = $null
try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [System.Windows.Forms.Application]::EnableVisualStyles()

    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = $env:KITVID_PICKER_TITLE
    $dialog.ShowNewFolderButton = $true
    if ($env:KITVID_PICKER_INITIAL) {
        $dialog.SelectedPath = $env:KITVID_PICKER_INITIAL
    }

    # A real but invisible owner window keeps the dialog in the foreground.
    # Without a shown owner, Windows often places the dialog behind the browser.
    $owner = New-Object System.Windows.Forms.Form
    $owner.Text = 'KitVid'
    $owner.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
    $owner.ShowInTaskbar = $false
    $owner.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
    $owner.Size = New-Object System.Drawing.Size(1, 1)
    $owner.Opacity = 0.01
    $owner.TopMost = $true
    $owner.Show()
    [System.Windows.Forms.Application]::DoEvents()
    $owner.Activate()

    $result = $dialog.ShowDialog($owner)

    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        Write-PickerFile $env:KITVID_PICKER_RESULT $dialog.SelectedPath
        $dialog.Dispose()
        $owner.Close()
        $owner.Dispose()
        exit 0
    }

    $dialog.Dispose()
    $owner.Close()
    $owner.Dispose()
    exit 2
}
catch {
    try {
        Write-PickerFile $env:KITVID_PICKER_ERROR $_.Exception.Message
    } catch {
    }
    if ($dialog) { try { $dialog.Dispose() } catch {} }
    if ($owner) { try { $owner.Close(); $owner.Dispose() } catch {} }
    exit 3
}
"""


class FolderPickerUnavailable(RuntimeError):
    pass


def _initial_dir(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        path = Path(os.path.expandvars(raw)).expanduser()
    except (OSError, ValueError, RuntimeError):
        return None
    if path.is_dir():
        return str(path)
    if path.parent.is_dir():
        return str(path.parent)
    return None


def _run(args: list[str], env: dict | None = None) -> tuple[int, str, str] | None:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=DIALOG_TIMEOUT_SECONDS,
            env=env,
        )
    except (FileNotFoundError, OSError):
        return None
    except subprocess.TimeoutExpired:
        return 124, "", "The folder picker timed out."
    return proc.returncode, proc.stdout, proc.stderr


def _read_result(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError):
        return ""


def _encode_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _pick_zenity(initial: str | None) -> tuple[bool, str | None]:
    zenity = shutil.which("zenity")
    if not zenity:
        return False, None

    args = [zenity, "--file-selection", "--directory", "--title", TITLE]
    if initial:
        args.append(f"--filename={initial.rstrip(os.sep)}{os.sep}")

    result = _run(args)
    if result is None:
        return False, None
    code, stdout, _ = result
    if code == 0:
        return True, stdout.strip() or None
    if code == 1:
        return True, None
    return False, None


def _pick_kdialog(initial: str | None) -> tuple[bool, str | None]:
    kdialog = shutil.which("kdialog")
    if not kdialog:
        return False, None

    args = [kdialog, "--title", TITLE, "--getexistingdirectory"]
    if initial:
        args.append(initial)
    result = _run(args)
    if result is None:
        return False, None
    code, stdout, _ = result
    if code == 0:
        return True, stdout.strip() or None
    if code == 1:
        return True, None
    return False, None


def _pick_tk(initial: str | None) -> tuple[bool, str | None]:
    script = (
        "import os\n"
        "import tkinter as tk\n"
        "from tkinter import filedialog\n"
        "root = tk.Tk()\n"
        "if os.name == 'nt':\n"
        "    try:\n"
        "        root.overrideredirect(True)\n"
        "        screen_x = root.winfo_screenwidth() // 2\n"
        "        screen_y = root.winfo_screenheight() // 2\n"
        "        root.geometry('1x1+%d+%d' % (screen_x, screen_y))\n"
        "        root.attributes('-topmost', True)\n"
        "        try:\n"
        "            root.attributes('-alpha', 0.01)\n"
        "        except tk.TclError:\n"
        "            pass\n"
        "        root.update()\n"
        "        root.lift()\n"
        "        root.focus_force()\n"
        "    except tk.TclError:\n"
        "        pass\n"
        "else:\n"
        "    root.withdraw()\n"
        "    try:\n"
        "        root.attributes('-topmost', True)\n"
        "    except tk.TclError:\n"
        "        pass\n"
        "try:\n"
        "    path = filedialog.askdirectory(\n"
        "        parent=root,\n"
        "        title=os.environ.get('KITVID_PICKER_TITLE', 'Choose a folder'),\n"
        "        initialdir=os.environ.get('KITVID_PICKER_INITIAL') or None,\n"
        "        mustexist=True,\n"
        "    )\n"
        "    if path:\n"
        "        with open(os.environ['KITVID_PICKER_RESULT'], 'w', encoding='utf-8') as handle:\n"
        "            handle.write(path)\n"
        "finally:\n"
        "    root.destroy()\n"
    )

    with tempfile.TemporaryDirectory(prefix="kitvid-picker-") as temp:
        result_file = Path(temp) / "selected.txt"
        env = os.environ.copy()
        env["KITVID_PICKER_TITLE"] = TITLE
        env["KITVID_PICKER_INITIAL"] = initial or ""
        env["KITVID_PICKER_RESULT"] = str(result_file)

        result = _run([sys.executable, "-c", script], env=env)
        if result is None:
            return False, None
        code, _, _ = result
        if code == 0:
            return True, _read_result(result_file) or None
        return False, None


def _pick_macos(initial: str | None) -> tuple[bool, str | None]:
    osascript = shutil.which("osascript")
    if not osascript:
        return False, None

    prompt = TITLE.replace("\\", "\\\\").replace('"', '\\"')
    script = f'POSIX path of (choose folder with prompt "{prompt}"'
    if initial:
        quoted = initial.replace("\\", "\\\\").replace('"', '\\"')
        script += f' default location (POSIX file "{quoted}")'
    script += ")"

    result = _run([osascript, "-e", script])
    if result is None:
        return False, None
    code, stdout, _ = result
    if code == 0:
        return True, stdout.strip() or None
    if code == 1:
        return True, None
    return False, None


def _pick_windows(initial: str | None) -> str | None:
    last_error = ""
    powershell = shutil.which("powershell") or shutil.which("pwsh")

    if powershell:
        with tempfile.TemporaryDirectory(prefix="kitvid-picker-") as temp:
            temp_path = Path(temp)
            result_file = temp_path / "selected.txt"
            error_file = temp_path / "error.txt"

            env = os.environ.copy()
            env["KITVID_PICKER_TITLE"] = TITLE
            env["KITVID_PICKER_INITIAL"] = initial or ""
            env["KITVID_PICKER_RESULT"] = str(result_file)
            env["KITVID_PICKER_ERROR"] = str(error_file)

            encoded = _encode_powershell(WINDOWS_PICKER_SCRIPT)
            result = _run(
                [powershell, "-NoProfile", "-STA", "-EncodedCommand", encoded],
                env=env,
            )

            if result is not None:
                code, _, stderr = result
                if code == 0:
                    selected = _read_result(result_file)
                    if selected:
                        return selected
                    last_error = "The folder dialog did not return a path."
                elif code == 2:
                    return None
                elif code == 124:
                    last_error = stderr.strip() or "The folder picker timed out."
                else:
                    last_error = (
                        _read_result(error_file)
                        or stderr.strip()
                        or "The folder dialog could not be shown."
                    )
            else:
                last_error = "PowerShell could not be started."

    # PowerShell is missing or failed: try the Tk dialog before giving up.
    handled, path = _pick_tk(initial)
    if handled:
        return path

    message = "Could not open a folder picker. Type the folder path manually."
    if last_error:
        message = f"{message} ({last_error})"
    raise FolderPickerUnavailable(message)


def pick_folder(initial_dir: str | None = None) -> str | None:
    fake = os.environ.get("VD_FOLDER_PICKER_FAKE")
    if fake is not None:
        if fake.strip().lower() in ("", "cancel", "none"):
            return None
        return str(Path(fake).expanduser().resolve())

    initial = _initial_dir(initial_dir)

    if sys.platform.startswith("win"):
        return _pick_windows(initial)

    if sys.platform == "darwin":
        handled, path = _pick_macos(initial)
        if handled:
            return path
        handled, path = _pick_tk(initial)
        if handled:
            return path
        raise FolderPickerUnavailable(
            "Could not open a folder picker. Type the folder path manually."
        )

    handled, path = _pick_zenity(initial)
    if handled:
        return path
    handled, path = _pick_kdialog(initial)
    if handled:
        return path
    handled, path = _pick_tk(initial)
    if handled:
        return path

    raise FolderPickerUnavailable(
        "Could not open a folder picker. Install zenity or kdialog, "
        "or type the folder path manually."
    )
