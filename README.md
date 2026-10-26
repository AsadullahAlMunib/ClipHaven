# ClipHaven (`v2.0.0`)

![CI Status](https://img.shields.io/badge/CI-passing-brightgreen)
![Release](https://img.shields.io/badge/version-v2.0.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

**Catch, keep, and enjoy your clips.**

ClipHaven is a fast, beginner-friendly, local-only video and audio downloader for Windows (with cross-platform Python support) powered by [`yt-dlp`](https://github.com/yt-dlp/yt-dlp). It runs 100% locally on your computer (`127.0.0.1`) with a clean dark/light web interface—no ads, no external servers, and no tracking.

---

## ✨ Key Features

- **Dual Launch Options**:
  - **Option A — Standalone `ClipHaven.exe`**: Run directly on Windows with zero Python installation required.
  - **Option B — One-Click `setup-and-run.bat`**: Automatically creates `.venv`, installs/updates `yt-dlp`, checks `FFmpeg`, and launches the app.
- **Effortless 4-Step Workflow**: Paste Link → Choose Format → Choose Quality → Click **Download Now**.
- **Instant Video Preview**: Automatically displays the video thumbnail, title, channel name, duration, and playlist count as soon as you paste a link.
- **One-Click Paste & Smart Link Extraction**: Click **📋 Paste** (or paste messy share text from mobile apps) and ClipHaven automatically extracts the clean video URL.
- **Multi-Platform Support**:
  - **YouTube** (`youtube.com`, `youtu.be`, Shorts, Playlists)
  - **Facebook** (`facebook.com`, `fb.watch`, Reels)
  - **Instagram** (`instagram.com` Reels & Posts)
  - **TikTok**, **X (Twitter)**, **Reddit**, **Vimeo**, **Dailymotion**, and **Twitch**
- **Video & Audio Formats**:
  - **Video**: `MP4` (Recommended), `MKV`, `WEBM`
  - **Audio Only**: `MP3`, `M4A`, `WAV` (automatically disables the video quality selector)
- **Up to 4K Resolution**: Choose `Best Available`, `4K (2160p)`, `2K (1440p)`, `1080p`, `720p`, `480p`, or `360p (Data Saver)`.
- **Live Progress, Speed & ETA**: Real-time download speed (`⚡ MB/s`), remaining time (`⏱ ETA`), and clear stage badges (`Downloading video`, `Downloading audio track`, `Merging`).
- **One-Click Open Folder & Recent History**: Click **📂 Open Folder** when a download finishes to highlight the saved file in Windows Explorer, or revisit files from the **Recent Downloads** list.
- **Collapsible Extra Options (`⚙️ Cut Clip / Extra Options`)**:
  - **✂️ Cut Clip (Time Range)**: Download only a specific portion of a video (e.g., `01:15` to `02:30`) instead of the entire file.
  - **Subtitles (CC)**: Download and embed English/Bangla subtitles into your video.
  - **Embed Cover Art / Thumbnail**: Attach the video thumbnail as cover art.
  - **Playlist Support**: Toggle full playlist downloading with one click.
  - **Browser Login Cookies**: Use your existing login from **Chrome**, **Edge**, **Firefox**, **Brave**, or **Opera** to download private or age-restricted videos you are authorized to access.

---

## 🚀 Quick Start (Choose Either Method)

### Method 1: Standalone `.exe` (No Python Required)
1. Go to the **Releases** page of this repository and download **`ClipHaven-Windows-EXE.zip`** (or build it locally by double-clicking **`build-exe.bat`**).
2. Extract the zip folder and double-click **`ClipHaven.exe`**.
3. Your browser will open `http://127.0.0.1:8765/` automatically.

### Method 2: Source `.zip` + `setup-and-run.bat` (Auto-Updates `yt-dlp`)
1. Install **Python 3.10+** from [python.org/downloads](https://www.python.org/downloads/) and make sure **"Add Python to PATH"** is checked.
2. Download and extract the repository `.zip`.
3. Double-click **`setup-and-run.bat`**.
4. Wait a moment while it sets up `.venv`, installs/upgrades `yt-dlp`, and checks for `FFmpeg`. Your browser will open `http://127.0.0.1:8765/` automatically.

---

## 🛠️ Manual Setup & Building `.exe` Locally

```bash
# Run from Python directly:
python -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip -r requirements.txt
.venv\Scripts\python.exe server.py

# Or build ClipHaven.exe yourself on Windows:
build-exe.bat
```

---

## 📖 How to Use

1. **Paste a Link**: Click **📋 Paste** or paste any supported video link into **1. Video Link**. A preview card will appear with the video's title, thumbnail, and duration.
2. **Select Format & Quality**: Choose your desired **Format** (`MP4`, `MP3`, etc.) and **Video Quality** (`Best Available`, `4K`, `1080p`, etc.).
3. **Choose Save Folder**: Keep the default folder or click **📁 Browse…** to pick a custom folder (ClipHaven remembers your choice).
4. **Optional — Cut Clip or Extra Options**:
   - Click **⚙️ Cut Clip / Extra Options** to expand advanced tools.
   - Enter **Start Time** (e.g., `01:15`) and **End Time** (e.g., `02:30`) to save only that clip.
   - Check **Include Subtitles (CC)**, **Embed Cover Art**, or **Download Entire Playlist** if needed.
   - For private/age-restricted videos, choose your browser under **Use Browser Login**.
5. **Download**: Click **⬇ Download Now**. Watch live progress, speed, and ETA, then click **📂 Open Folder** when complete!

---

## 🤖 GitHub Actions & Automation Included

- **`.github/workflows/ci.yml`**: Runs `ruff` linting and `pytest` across **Windows, Ubuntu, and macOS** on Python `3.10`, `3.11`, and `3.12` on every push and pull request.
- **`.github/workflows/release.yml`**: Automatically builds both **`ClipHaven-Windows-EXE.zip`** (containing `ClipHaven.exe` + `setup-and-run.bat`) and **`ClipHaven-Source-Bat.zip`** whenever you push a version tag (e.g., `git tag v2.0.0 && git push origin v2.0.0`) or trigger the workflow manually from the GitHub **Actions** tab.
- **`.github/dependabot.yml`**: Automatically checks weekly for `yt-dlp` and GitHub Actions updates and opens Pull Requests.

---

## 📂 Project Structure

```text
ClipHaven/
├── index.html                   # Clean, responsive UI markup
├── style.css                    # Dark/light theme tokens and component styling
├── app.js                       # Frontend logic (auto-preview, polling, history, persistence)
├── server.py                    # Local-only Python backend (supports both .py and frozen .exe)
├── setup-and-run.bat            # One-click Windows Python venv setup & launcher
├── build-exe.bat                # One-click local builder to generate dist\ClipHaven.exe
├── requirements.txt             # Python runtime dependencies (yt-dlp)
├── pyproject.toml               # Project metadata & version configuration (v2.0.0)
├── CHANGELOG.md                 # Release history and version notes
├── LICENSE                      # MIT License
├── .github/
│   ├── dependabot.yml           # Weekly automated dependency update checks
│   └── workflows/
│       ├── ci.yml               # Multi-OS linting & test matrix
│       └── release.yml          # Automated Windows .exe & .zip GitHub Release builder
└── tests/
    └── test_server.py           # Automated unit & API endpoint tests
```

---

## 📄 License

Licensed under the [MIT License](LICENSE).
