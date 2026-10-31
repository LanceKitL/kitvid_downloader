@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "SELF=%~f0"
set "MARK_ACTIVE=%ROOT%.setup_active.tmp"
set "MARK_FFMPEG=%ROOT%.setup_ffmpeg.tmp"
set "MARK_VENV=%ROOT%.setup_venv.tmp"
set "FFMPEG_DIR=%ROOT%tools\ffmpeg"
set "FFMPEG_ZIP=%TEMP%\kitvid-ffmpeg.zip"
set "PY_INSTALLER=%TEMP%\kitvid-python-installer.exe"
set "KV_SELF=%SELF%"
set "KV_ACTIVE=%MARK_ACTIVE%"

if /i "%~1"=="--cleanup" goto :cleanup_mode

REM ---------- Clean up after an interrupted run ----------
if exist "%MARK_ACTIVE%" echo Previous setup was interrupted. Cleaning up...
call :cleanup_partial

if not exist "requirements.txt" goto :no_requirements

REM ---------- Step 1: FFmpeg ----------
call :ensure_ffmpeg
if errorlevel 1 goto :ffmpeg_error

REM ---------- Step 2: Python ----------
set "PYTHON_EXE="
call :find_python
if defined PYTHON_EXE goto :python_ready

echo.
echo Python 3.11-3.13 not found. Downloading Python 3.12...
call :start_watcher
curl.exe -L --fail --progress-bar -o "%PY_INSTALLER%" https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
if errorlevel 1 goto :python_download_fail

echo Installing Python 3.12. This takes about a minute...
start /wait "" "%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
if errorlevel 1 goto :python_install_fail
del /q "%PY_INSTALLER%" >nul 2>&1

call :find_python
if defined PYTHON_EXE goto :python_ready

echo.
echo Python was installed, but this window cannot see it yet.
echo Close this window and run the file again.
call :finish_markers
pause
exit /b 1

:python_ready
echo Using Python: %PYTHON_EXE%

REM ---------- Step 3: Virtual environment ----------
if not exist ".venv\Scripts\python.exe" goto :make_venv
".venv\Scripts\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 goto :venv_broken
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1
if errorlevel 1 goto :venv_broken
goto :venv_ready

:venv_broken
echo Existing virtual environment is broken or uses an unsupported Python. Recreating...
call :start_watcher
type nul > "%MARK_VENV%"
rmdir /s /q ".venv"

:make_venv
call :start_watcher
type nul > "%MARK_VENV%"
echo Creating virtual environment...
%PYTHON_EXE% -m venv .venv
if errorlevel 1 goto :setup_error
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :setup_error

:venv_ready

REM ---------- Step 4: Python packages and yt-dlp ----------
echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :setup_error

if not exist ".venv\Scripts\yt-dlp.exe" ".venv\Scripts\python.exe" -m pip install -U yt-dlp
if errorlevel 1 goto :setup_error

set "PATH=%ROOT%.venv\Scripts;%PATH%"
set "VD_YTDLP=%ROOT%.venv\Scripts\yt-dlp.exe"

yt-dlp --version >nul 2>&1
if errorlevel 1 goto :ytdlp_error

REM ---------- Setup finished: nothing to clean up anymore ----------
call :finish_markers

REM ---------- Launch ----------
".venv\Scripts\python.exe" launcher.py
if errorlevel 1 pause
exit /b 0


REM ======================================================================
REM  Error exits
REM ======================================================================

:no_requirements
echo requirements.txt not found in %ROOT%
pause
exit /b 1

:ffmpeg_error
echo.
echo FFmpeg could not be installed automatically.
echo Download "release essentials" from https://www.gyan.dev/ffmpeg/builds/
echo and extract it so that ffmpeg.exe ends up at:
echo   %FFMPEG_DIR%\bin\ffmpeg.exe
echo Then run this file again.
echo.
pause
exit /b 1

:python_download_fail
echo.
echo Python download failed. Check your internet connection, or install
echo Python 3.12 manually from https://www.python.org/downloads/
del /q "%PY_INSTALLER%" >nul 2>&1
call :finish_markers
pause
exit /b 1

:python_install_fail
echo.
echo Python installation failed.
del /q "%PY_INSTALLER%" >nul 2>&1
call :finish_markers
pause
exit /b 1

:ytdlp_error
echo.
echo yt-dlp could not be started from %ROOT%.venv\Scripts

:setup_error
echo.
echo Setup failed. Scroll up for the actual error message.
echo Common causes: no internet, Python version incompatible with a package, missing build tools.
echo.
if exist "%MARK_VENV%" rmdir /s /q "%ROOT%.venv" >nul 2>&1
call :finish_markers
pause
exit /b 1


REM ======================================================================
REM  Helpers
REM ======================================================================

:find_python
for %%V in (3.13 3.12 3.11) do (
  if not defined PYTHON_EXE (
    py -%%V -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=py -%%V"
  )
)
for %%V in (313 312 311) do (
  if not defined PYTHON_EXE (
    if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" set PYTHON_EXE="%LocalAppData%\Programs\Python\Python%%V\python.exe"
  )
)
exit /b 0

:ensure_ffmpeg
where ffmpeg >nul 2>&1
if not errorlevel 1 exit /b 0
if exist "%FFMPEG_DIR%\bin\ffmpeg.exe" goto :ffmpeg_set_path

echo.
echo FFmpeg not found. Installing it before the other dependencies...
call :start_watcher
type nul > "%MARK_FFMPEG%"

REM Primary source. Gives up if the speed stays under ~100 KB/s for 20 seconds.
curl.exe -L --fail --progress-bar --connect-timeout 15 --speed-limit 102400 --speed-time 20 -o "%FFMPEG_ZIP%" https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
if not errorlevel 1 goto :ffmpeg_extract
echo.
echo Primary download was slow or failed. Trying the GitHub mirror...
curl.exe -L --fail --progress-bar --connect-timeout 15 -o "%FFMPEG_ZIP%" https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip
if errorlevel 1 goto :ffmpeg_fail

:ffmpeg_extract
echo Extracting FFmpeg...
rmdir /s /q "%FFMPEG_DIR%_tmp" >nul 2>&1
mkdir "%FFMPEG_DIR%_tmp"
tar.exe -xf "%FFMPEG_ZIP%" -C "%FFMPEG_DIR%_tmp" "*/bin/*"
if errorlevel 1 goto :ffmpeg_fail
mkdir "%FFMPEG_DIR%\bin" >nul 2>&1
for /d %%D in ("%FFMPEG_DIR%_tmp\*") do xcopy /e /i /y "%%D\bin\*" "%FFMPEG_DIR%\bin\" >nul
rmdir /s /q "%FFMPEG_DIR%_tmp" >nul 2>&1
del /q "%FFMPEG_ZIP%" >nul 2>&1
if not exist "%FFMPEG_DIR%\bin\ffmpeg.exe" goto :ffmpeg_fail

:ffmpeg_set_path
set "PATH=%FFMPEG_DIR%\bin;%PATH%"
exit /b 0

:ffmpeg_fail
call :cleanup_partial
exit /b 1

REM Starts a hidden background watcher (once). If this window is closed or the
REM batch job is cancelled before setup finishes, the watcher runs this script
REM again with --cleanup to remove what this run created.
:start_watcher
if exist "%MARK_ACTIVE%" exit /b 0
type nul > "%MARK_ACTIVE%"
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "$p=(Get-CimInstance Win32_Process -Filter ('ProcessId='+$PID)).ParentProcessId; while ((Get-Process -Id $p -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath $env:KV_ACTIVE)) { Start-Sleep -Seconds 2 }; if (Test-Path -LiteralPath $env:KV_ACTIVE) { Start-Sleep -Seconds 2; cmd /c call $env:KV_SELF --cleanup }"
exit /b 0

:finish_markers
del /q "%MARK_FFMPEG%" >nul 2>&1
del /q "%MARK_VENV%" >nul 2>&1
del /q "%MARK_ACTIVE%" >nul 2>&1
exit /b 0

:cleanup_partial
if exist "%MARK_FFMPEG%" call :remove_ffmpeg
if exist "%MARK_VENV%" call :remove_venv
del /q "%FFMPEG_ZIP%" >nul 2>&1
del /q "%PY_INSTALLER%" >nul 2>&1
if exist "%MARK_FFMPEG%" exit /b 1
if exist "%MARK_VENV%" exit /b 1
del /q "%MARK_ACTIVE%" >nul 2>&1
exit /b 0

:remove_ffmpeg
rmdir /s /q "%FFMPEG_DIR%" >nul 2>&1
rmdir /s /q "%FFMPEG_DIR%_tmp" >nul 2>&1
if exist "%FFMPEG_DIR%" exit /b 1
rmdir "%ROOT%tools" >nul 2>&1
del /q "%MARK_FFMPEG%" >nul 2>&1
exit /b 0

:remove_venv
rmdir /s /q "%ROOT%.venv" >nul 2>&1
if exist "%ROOT%.venv" exit /b 1
del /q "%MARK_VENV%" >nul 2>&1
exit /b 0

:cleanup_mode
set "TRIES=0"
:cleanup_retry
call :cleanup_partial
if not errorlevel 1 exit /b 0
set /a TRIES+=1
if %TRIES% GEQ 5 exit /b 0
ping -n 3 127.0.0.1 >nul
goto :cleanup_retry