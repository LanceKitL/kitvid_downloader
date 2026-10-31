@echo off
setlocal
cd /d "%~dp0"

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

echo Checking dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :setup_error

REM Make sure yt-dlp exists in the venv
if not exist ".venv\Scripts\yt-dlp.exe" (
  echo Installing yt-dlp...
  ".venv\Scripts\python.exe" -m pip install -U yt-dlp
  if errorlevel 1 goto :setup_error
)

REM Put the venv Scripts folder on PATH for this session and tell the app where yt-dlp is
set "PATH=%~dp0.venv\Scripts;%PATH%"
set "VD_YTDLP=%~dp0.venv\Scripts\yt-dlp.exe"

yt-dlp --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo yt-dlp could not be started from %~dp0.venv\Scripts
  goto :setup_error
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo.
  echo WARNING: FFmpeg not found. Download it from https://www.gyan.dev/ffmpeg/builds/
  echo Get the "release essentials" zip, extract it, and add its bin folder to PATH.
  echo.
)

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