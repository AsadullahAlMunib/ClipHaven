# ClipHaven
Catch, keep, and enjoy your clips.

A local-only Windows tool for downloading YouTube and Facebook videos via a browser UI backed by `yt-dlp`. The backend binds to `127.0.0.1` only.

## Features
- Browser UI at `http://127.0.0.1:8765/`
- Quality selection: best, 1080p, 720p, 480p
- Output formats: MP4, MKV, WEBM, MP3, M4A, WAV
- Folder picker and default `D:\Videos\Downloads`
- Live progress with status pill and progress bar
- Cancel in-progress downloads
- Light/dark theme toggle (persisted in browser)
- One-click setup via `setup-and-run.bat`

## Requirements
- Windows 10/11
- Python 3.10+
- FFmpeg (recommended, for merging high-quality streams)
- Internet connection

## Quick Start
1. Install Python 3.10+ from https://www.python.org/downloads/ and enable "Add Python to PATH".
2. Extract this folder.
3. Double-click `setup-and-run.bat`.
4. Wait for setup to finish; the browser opens automatically.
5. Paste an authorized YouTube/Facebook URL, choose folder/quality/format, then click **Start download**.

`setup-and-run.bat` will:
- Check Python
- Create `.venv`
- Install Python dependencies
- Attempt FFmpeg install via winget if missing
- Launch the app

## Manual Setup
```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe server.py
```
Then open `http://127.0.0.1:8765/` in your browser.

## Using the Tool
1. Paste a YouTube or Facebook video URL into **Video URL**.
2. Set the **Save folder** (default `D:\Videos\Downloads`), or click **Choose folder…** to pick one.
3. Pick an **Output format** (MP4/MKV/WEBM for video; MP3/M4A/WAV for audio).
4. Pick a **Video quality** (disabled for audio formats).
5. Click **Start download**. Progress, state, and details appear in the status panel.
6. Click **Cancel** to stop an in-progress download.
7. When complete, the file is saved to the chosen folder.

Notes:
- Audio-only formats disable the quality selector.
- The backend runs locally; nothing is uploaded.
- FFmpeg is recommended for merging high-quality separate audio/video streams.
- Press `Ctrl+C` in the server terminal to stop the app.

## FFmpeg
FFmpeg is required for merging high-quality separate audio/video streams. If not installed, the script tries winget; otherwise install manually:
- https://ffmpeg.org/download.html
- Ensure `ffmpeg` is on PATH, then restart the app.

## Files
- `index.html` — UI markup
- `style.css` — styles (theme tokens, layout, components)
- `app.js` — frontend logic (API calls, progress polling, theme toggle)
- `server.py` — local backend and progress API
- `requirements.txt` — Python dependencies (yt-dlp)
- `setup-and-run.bat` — setup and launch

## Troubleshooting
- Setup fails: run in Command Prompt:
  `py -m pip install -r requirements.txt` then `py server.py`
- Update yt-dlp:
  `py -m pip install -U yt-dlp`
- Port 8765 already in use: the server will exit with a clear error message. Close the existing instance or change the port in `server.py`.
- Facebook videos may require login or be unavailable; this app does not bypass access controls.
- Only download videos you own or have permission to save. No DRM/paywall bypass.
- If the page looks unstyled, ensure `style.css` and `app.js` are next to `index.html` and the server is running.

## License
MIT License - see [LICENSE](LICENSE) file for details.
