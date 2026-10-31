import os
import shutil
import subprocess
import sys
from pathlib import Path

TITLE = "Choose a download folder"
DIALOG_TIMEOUT_SECONDS = 600


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
            timeout=DIALOG_TIMEOUT_SECONDS,
            env=env,
        )
    except (FileNotFoundError, OSError):
        return None
    except subprocess.TimeoutExpired:
        return 124, "", "The folder picker timed out."
    return proc.returncode, proc.stdout, proc.stderr


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
        "root.withdraw()\n"
        "try:\n"
        "    root.attributes('-topmost', True)\n"
        "except tk.TclError:\n"
        "    pass\n"
        "path = filedialog.askdirectory(\n"
        "    parent=root,\n"
        "    title=os.environ.get('KITVID_PICKER_TITLE', 'Choose a folder'),\n"
        "    initialdir=os.environ.get('KITVID_PICKER_INITIAL') or None,\n"
        "    mustexist=True,\n"
        ")\n"
        "print(path or '')\n"
        "root.destroy()\n"
    )
    env = os.environ.copy()
    env["KITVID_PICKER_TITLE"] = TITLE
    env["KITVID_PICKER_INITIAL"] = initial or ""

    result = _run([sys.executable, "-c", script], env=env)
    if result is None:
        return False, None
    code, stdout, _ = result
    if code == 0:
        return True, stdout.strip() or None
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
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell:
        selected = initial.replace("'", "''") if initial else ""
        script = (
            "Add-Type -AssemblyName System.Windows.Forms\n"
            "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog\n"
            f"$dialog.Description = '{TITLE}'\n"
            "$dialog.ShowNewFolderButton = $true\n"
        )
        if selected:
            script += f"$dialog.SelectedPath = '{selected}'\n"
        script += (
            "$owner = New-Object System.Windows.Forms.Form\n"
            "$owner.TopMost = $true\n"
            "$owner.ShowInTaskbar = $false\n"
            "$result = $dialog.ShowDialog($owner)\n"
            "if ($result -eq [System.Windows.Forms.DialogResult]::OK) {\n"
            "  Write-Output $dialog.SelectedPath\n"
            "}\n"
        )
        result = _run([powershell, "-NoProfile", "-STA", "-Command", script])
        if result is not None:
            code, stdout, _ = result
            if code == 0:
                return stdout.strip() or None

    handled, path = _pick_tk(initial)
    if handled:
        return path
    raise FolderPickerUnavailable(
        "Could not open a folder picker. Type the folder path manually."
    )


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
