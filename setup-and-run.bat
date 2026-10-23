@echo off
setlocal
cd /d "%~dp0"

:: Python check
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ was not found.
  echo Install it from https://www.python.org/downloads/ and enable "Add Python to PATH".
  start "" "https://www.python.org/downloads/"
  pause
  exit /b 1
)

:: Create venv
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 (echo Could not create virtual environment. & pause & exit /b 1)
)

:: Upgrade pip + install deps
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo Dependency install failed. & pause & exit /b 1)

:: FFmpeg check/install
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo FFmpeg not found. Trying winget install...
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  where ffmpeg >nul 2>nul
  if errorlevel 1 (
    echo FFmpeg could not be installed automatically.
    echo Please install FFmpeg manually and add it to PATH for best results.
    echo See: https://ffmpeg.org/download.html
  ) else (
    echo FFmpeg installed successfully.
  )
) else (
  echo FFmpeg already available.
)

:: Launch
".venv\Scripts\python.exe" server.py
pause
