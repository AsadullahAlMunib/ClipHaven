@echo off
setlocal
cd /d "%~dp0"

:: Python check
where py >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.10+ was not found.
    echo Install it from https://www.python.org/downloads/ and enable "Add Python to PATH".
    start "" "https://www.python.org/downloads/"
    pause
    exit /b 1
  )
)

set "USE_VENV=0"

:: Try to create/use venv
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv >nul 2>&1 || python -m venv .venv
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
    py -3 -m venv .venv >nul 2>&1 || python -m venv .venv
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

set "USE_VENV=1"
goto :install

:use_system
echo Using system Python instead of venv.
set "USE_VENV=0"

:install
if "%USE_VENV%"=="1" (
  echo Using virtual environment: .venv\Scripts\python.exe
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 (
    echo Failed to upgrade pip.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade -r requirements.txt
  if errorlevel 1 (
    echo Dependency install failed.
    pause
    exit /b 1
  )
) else (
  echo Using system Python
  py -3 -m pip install --upgrade pip || python -m pip install --upgrade pip
  py -3 -m pip install --upgrade -r requirements.txt || python -m pip install --upgrade -r requirements.txt
  if errorlevel 1 (
    echo Dependency install failed.
    pause
    exit /b 1
  )
)

:: FFmpeg check/install
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo FFmpeg not found on PATH. Trying winget install...
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  :: Refresh user/system PATH in current session
  for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%B"
  for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%B"
  set "PATH=%SYS_PATH%;%USR_PATH%;%PATH%"
  where ffmpeg >nul 2>&1
  if errorlevel 1 (
    echo Note: FFmpeg will be detected automatically by ClipHaven if installed via Winget, or restart this window after installing FFmpeg.
  ) else (
    echo FFmpeg installed and ready.
  )
) else (
  echo FFmpeg already available.
)

:: Launch
echo Starting ClipHaven...
if "%USE_VENV%"=="1" (
  ".venv\Scripts\python.exe" server.py
) else (
  py -3 server.py || python server.py
)
pause
