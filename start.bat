@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE="
where py >nul 2>&1
if not errorlevel 1 set "PYTHON_EXE=py -3"

if not defined PYTHON_EXE (
  where python >nul 2>&1
  if not errorlevel 1 set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
  echo.
  echo Python 3.11+ was not found.
  echo Install it from https://www.python.org/downloads/ and enable "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PYTHON_EXE% -m venv .venv
  if errorlevel 1 goto :setup_error
  echo Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 goto :setup_error
)

echo Checking dependencies...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 goto :setup_error

".venv\Scripts\python.exe" launcher.py
if errorlevel 1 pause
exit /b 0

:setup_error
echo.
echo Setup failed. Make sure Python 3.11+ is installed and you have an internet connection.
echo FFmpeg is also required: winget install Gyan.FFmpeg
echo.
pause
exit /b 1
