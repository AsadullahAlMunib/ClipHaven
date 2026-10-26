@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo   ClipHaven Standalone .exe Builder (PyInstaller)
echo ===================================================

set "PYEXE=python"
if exist ".venv\Scripts\python.exe" (
  set "PYEXE=.venv\Scripts\python.exe"
) else (
  where py >nul 2>nul && set "PYEXE=py -3"
)

echo [1/3] Installing/updating requirements and PyInstaller...
%PYEXE% -m pip install --upgrade pip -r requirements.txt pyinstaller
if errorlevel 1 (
  echo Failed to install PyInstaller or dependencies.
  pause
  exit /b 1
)

echo [2/3] Building standalone ClipHaven.exe...
%PYEXE% -m PyInstaller --noconfirm --clean --onefile --name ClipHaven ^
  --add-data "index.html;." ^
  --add-data "style.css;." ^
  --add-data "app.js;." ^
  --collect-all yt_dlp ^
  server.py

if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)

echo [3/3] Copying ClipHaven.exe to project folder...
copy /y "dist\ClipHaven.exe" "ClipHaven.exe" >nul

echo.
echo Done! You can now double-click "ClipHaven.exe" OR "setup-and-run.bat" to launch ClipHaven.
pause
