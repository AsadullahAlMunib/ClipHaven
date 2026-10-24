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

set "PYEXE="

:: Try to create/use venv
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Failed to create virtual environment. Will use system Python.
    goto :use_system
  )
)

:: Check if venv has pip
".venv\Scripts\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo Virtual environment is missing pip. Attempting to repair...
  ".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>&1
  ".venv\Scripts\python.exe" -m pip --version >nul 2>&1
  if errorlevel 1 (
    echo Could not repair venv. Deleting and recreating...
    rmdir /s /q .venv >nul 2>&1
    py -3 -m venv .venv
    if errorlevel 1 (
      echo Failed to recreate venv. Will use system Python.
      goto :use_system
    )
    ".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>&1
    ".venv\Scripts\python.exe" -m pip --version >nul 2>&1
    if errorlevel 1 (
      echo Still missing pip. Will use system Python.
      goto :use_system
    )
  )
)

set "PYEXE=.venv\Scripts\python.exe"
goto :install

:use_system
echo Using system Python (py -3) instead of venv.
set "PYEXE=py -3"

:install
echo Using: %PYEXE%
"%PYEXE%" -m pip install --upgrade pip
if errorlevel 1 (
  echo Failed to upgrade pip.
  pause
  exit /b 1
)

"%PYEXE%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency install failed.
  pause
  exit /b 1
)

:: FFmpeg check/install
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo FFmpeg not found. Trying winget install...
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  where ffmpeg >nul 2>&1
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
echo Starting ClipHaven...
"%PYEXE%" server.py
pause
