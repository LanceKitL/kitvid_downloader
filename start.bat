@echo off
setlocal
cd /d "%~dp0"

REM ---------- Python ----------
set "PYTHON_EXE="
call :find_python
if defined PYTHON_EXE goto :python_ready

echo.
echo Python 3.11-3.13 not found. Downloading Python 3.12...
set "PY_INSTALLER=%TEMP%\python-3.12.10-amd64.exe"
curl.exe -L --fail -o "%PY_INSTALLER%" https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
if errorlevel 1 (
  echo.
  echo Download failed. Check your internet connection, or install
  echo Python 3.12 manually from https://www.python.org/downloads/
  pause
  exit /b 1
)

echo Installing Python 3.12. This takes about a minute...
start /wait "" "%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
if errorlevel 1 (
  echo.
  echo Python installation failed.
  pause
  exit /b 1
)
del "%PY_INSTALLER%" >nul 2>&1

call :find_python
if defined PYTHON_EXE goto :python_ready

echo.
echo Python was installed, but this window can't see it yet.
echo Close this window and run the file again.
pause
exit /b 1

:python_ready
echo Using Python: %PYTHON_EXE%

if not exist "requirements.txt" (
  echo requirements.txt not found in %cd%
  pause
  exit /b 1
)

REM ---------- Virtual environment ----------
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m pip --version >nul 2>&1
  if errorlevel 1 (
    echo Existing virtual environment is broken. Recreating...
    rmdir /s /q ".venv"
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PYTHON_EXE% -m venv .venv
  if errorlevel 1 goto :setup_error
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 goto :setup_error
)

REM ---------- Python packages and yt-dlp ----------
echo Checking dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :setup_error

if not exist ".venv\Scripts\yt-dlp.exe" (
  echo Installing yt-dlp...
  ".venv\Scripts\python.exe" -m pip install -U yt-dlp
  if errorlevel 1 goto :setup_error
)

set "PATH=%~dp0.venv\Scripts;%PATH%"
set "VD_YTDLP=%~dp0.venv\Scripts\yt-dlp.exe"

yt-dlp --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo yt-dlp could not be started from %~dp0.venv\Scripts
  goto :setup_error
)

REM ---------- FFmpeg ----------
call :ensure_ffmpeg
if errorlevel 1 goto :ffmpeg_error

REM ---------- Launch ----------
".venv\Scripts\python.exe" launcher.py
if errorlevel 1 pause
exit /b 0

:setup_error
echo.
echo Setup failed. Scroll up for the actual error message.
echo Common causes: no internet, Python version incompatible with a package, missing build tools.
echo.
pause
exit /b 1

:ffmpeg_error
echo.
echo FFmpeg could not be installed automatically.
echo Download "release essentials" from https://www.gyan.dev/ffmpeg/builds/
echo Extract it so that ffmpeg.exe ends up at:
echo   %~dp0tools\ffmpeg\bin\ffmpeg.exe
echo Then run this file again.
echo.
pause
exit /b 1

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

set "FFMPEG_DIR=%~dp0tools\ffmpeg"
if exist "%FFMPEG_DIR%\bin\ffmpeg.exe" goto :ffmpeg_path

echo.
echo FFmpeg not found. Downloading it (about 100 MB)...
set "FFMPEG_ZIP=%TEMP%\ffmpeg-release-essentials.zip"
curl.exe -L --fail -o "%FFMPEG_ZIP%" https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
if errorlevel 1 exit /b 1

echo Extracting FFmpeg...
if exist "%FFMPEG_DIR%_tmp" rmdir /s /q "%FFMPEG_DIR%_tmp"
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%FFMPEG_ZIP%' -DestinationPath '%FFMPEG_DIR%_tmp' -Force"
if errorlevel 1 exit /b 1

mkdir "%FFMPEG_DIR%\bin" >nul 2>&1
for /d %%D in ("%FFMPEG_DIR%_tmp\*") do xcopy /e /i /y "%%D\bin\*" "%FFMPEG_DIR%\bin\" >nul
rmdir /s /q "%FFMPEG_DIR%_tmp" >nul 2>&1
del "%FFMPEG_ZIP%" >nul 2>&1

if not exist "%FFMPEG_DIR%\bin\ffmpeg.exe" exit /b 1

:ffmpeg_path
set "PATH=%FFMPEG_DIR%\bin;%PATH%"
exit /b 0