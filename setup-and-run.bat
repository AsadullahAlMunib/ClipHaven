@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo   ClipHaven v3.1.2 — Local Video ^& Audio Downloader
echo   Developed by Md Asadullah Al Munib
echo   https://github.com/AsadullahAlMunib/ClipHaven/
echo ===================================================

:: Check for Python 3.10+
set "PY_CMD="
where py >nul 2>nul && (
  py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY_CMD=py -3"
)
if not defined PY_CMD (
  where python >nul 2>nul && (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY_CMD=python"
  )
)

if not defined PY_CMD (
  echo [ERROR] Python 3.10+ was not found on your computer.
  echo Please install Python 3.10 or newer from https://www.python.org/downloads/
  echo and check "Add Python to PATH" during installation.
  pause
  exit /b 1
)

:: Create virtual environment if needed
if not exist ".venv\Scripts\python.exe" (
  echo [1/2] Creating isolated Python environment ^(.venv^)...
  %PY_CMD% -m venv .venv
)

if exist ".venv\Scripts\python.exe" (
  set RUN_PY=".venv\Scripts\python.exe"
) else (
  set RUN_PY=%PY_CMD%
)

:: Install/update dependencies (includes yt-dlp and bundled FFmpeg via imageio-ffmpeg)
echo [2/2] Checking dependencies ^(yt-dlp ^& FFmpeg^)...
%RUN_PY% -m pip install --upgrade --quiet pip
%RUN_PY% -m pip install --upgrade --quiet -r requirements.txt
if errorlevel 1 (
  echo [WARN] Could not update packages online. Starting with existing packages...
)

echo.
echo Starting ClipHaven server...
%RUN_PY% server.py
pause
