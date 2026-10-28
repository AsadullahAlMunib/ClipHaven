# <img src="logo.svg" width="48" height="48" align="top" alt="ClipHaven logo" /> ClipHaven

**Catch, keep, and enjoy your clips — locally, safely, and effortlessly.**

![CI Status](https://img.shields.io/badge/CI-passing-brightgreen)
[![Release](https://img.shields.io/badge/version-v2.1.1-blue)](https://github.com/AsadullahAlMunib/ClipHaven/releases/tag/v2.1.1)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[✨ Features](#-key-features) • [⚡ Quick Download](#-quick-downloads) • [🚀 Getting Started](#-getting-started) • [📦 Releases](https://github.com/AsadullahAlMunib/ClipHaven/releases)

ClipHaven is a modern, high-speed, 100% local video and audio downloader powered by [`yt-dlp`](https://github.com/yt-dlp/yt-dlp). It runs privately on your computer (`127.0.0.1:8765`) through a clean dark/light web UI—**no ads, no tracking, no external server relays, and zero telemetry**.

## ⚡ Quick Downloads

| Package | Recommended For | Direct Link |
| ----- | ----- | ----- |
| **🚀 Windows Full App Bundle (`.zip`)** ⭐ **(Recommended)** | Complete Windows app with **all dependencies & `FFmpeg` included** (Antivirus-friendly, no Python required) | [⬇️ Download `ClipHaven-Windows-EXE.zip`](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest/download/ClipHaven-Windows-EXE.zip) |
| **📦 Standalone Windows App `.exe`** | Single portable executable (`ClipHaven.exe`) with embedded `FFmpeg` & zero setup | [⬇️ Download `ClipHaven.exe`](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest/download/ClipHaven.exe) |
| **⚡ Source + Launcher (`.bat`)** | Auto-updating `yt-dlp` & script usage on Windows (`setup-and-run.bat`) | [⬇️ Download `ClipHaven-Source-Bat.zip`](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest/download/ClipHaven-Source-Bat.zip) |
| **🌐 Cross-Platform Source** | Linux, macOS, or custom developer environments | [📦 View All Releases & Source Code](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest) |

## ✨ Key Features

### 💻 Three Flexible Launch Modes
* **Option A — Windows Full App Bundle (`ClipHaven-Windows-EXE.zip` — ⭐ Recommended):** Pre-packaged `--onedir` build containing `ClipHaven.exe`, `ffmpeg.exe`, and all runtime dependencies. Launches instantly without temporary unpacking or antivirus false positives.
* **Option B — Standalone Single Executable (`ClipHaven.exe`):** A single self-contained `.exe` file you can drop anywhere and double-click to run.
* **Option C — One-Click `setup-and-run.bat` (`ClipHaven-Source-Bat.zip`):** Automatically creates an isolated `.venv`, installs/updates `yt-dlp` and `imageio-ffmpeg`, and opens your default browser.

### 🌐 Wide Multi-Platform Extraction
Cleanly extracts video and audio from popular media platforms:
* **YouTube:** Full Videos, Shorts, and complete Playlists
* **Meta:** Facebook Videos & Reels, Instagram Reels & Posts
* **Others:** TikTok, X (Twitter), Reddit, Vimeo, Dailymotion, and Twitch

### 🎯 Precision Tools & Media Options
* **✂️ Video Trimming & Clip Cutter:** Download only the section you need by specifying `Start Time` and `End Time` (e.g., `01:15` to `02:30`).
* **💬 Multi-Language Subtitles (CC):** Download and embed English or Bangla subtitles directly into your video files.
* **🖼️ Embed Cover Art / Thumbnail:** Embed video thumbnails directly into downloaded media files.
* **📑 Playlist Downloads:** Download entire video playlists in batch with auto-detected item counts.
* **📋 Smart URL Sanitizer:** Strips out messy share text and metadata from mobile app links automatically.
* **⚡ Multiple Formats & 4K Quality:**
  * **Video Formats:** `MP4` *(Recommended)*, `MKV`, `WEBM`
  * **Audio Formats:** `MP3`, `M4A`, `WAV` (automatically disables irrelevant video resolution selectors)
  * **Resolutions:** `Best Available`, `4K (2160p)`, `2K (1440p)`, `1080p`, `720p`, `480p`, `360p`
* **📊 Real-Time Feedback:** Live download speed counters (`MB/s`), accurate remaining time (`ETA`), percentage progress bars, and post-download directory navigation (`📂 Open Folder`).

## 🚀 Getting Started

### Method 1: Windows Full App Bundle (⭐ Recommended)
1. Download [`ClipHaven-Windows-EXE.zip`](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest/download/ClipHaven-Windows-EXE.zip) from [Releases](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest).
2. Extract the archive into any folder.
3. Open the `ClipHaven` folder and double-click **`ClipHaven.exe`**. Your default browser will immediately open `http://127.0.0.1:8765/`.

### Method 2: Standalone Windows App (`ClipHaven.exe`)
1. Download [`ClipHaven.exe`](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest/download/ClipHaven.exe) directly from [Releases](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest).
2. Double-click **`ClipHaven.exe`** to launch the web dashboard at `http://127.0.0.1:8765/`.

### Method 3: One-Click Script (`setup-and-run.bat`)
1. Verify that **Python 3.10+** is installed with the **"Add Python to PATH"** checkbox selected during setup.
2. Download and extract [`ClipHaven-Source-Bat.zip`](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest/download/ClipHaven-Source-Bat.zip) (or clone the repository):
   ```bash
   git clone https://github.com/AsadullahAlMunib/ClipHaven.git
   cd ClipHaven
   ```
3. Double-click **`setup-and-run.bat`**. The script manages virtual environment creation, installs `yt-dlp` and portable `FFmpeg` (`imageio-ffmpeg`), and opens the dashboard automatically.

### Method 4: Cross-Platform & Developer Setup (macOS / Linux / Windows)
```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate

# 2. Install dependencies (includes yt-dlp and imageio-ffmpeg)
pip install --upgrade pip
pip install -r requirements.txt pytest

# 3. Launch server
python server.py

# 4. (Optional) Run tests locally
pytest -v
```

## 🤖 CI/CD & Repository Automation

This repository includes continuous integration workflows:

* [**`ci.yml`**](.github/workflows/ci.yml): Executes syntax linting with `ruff` and runs full test suites via `pytest` across **Windows, Ubuntu, and macOS** on Python `3.10`, `3.11`, and `3.12`.

* [**`release.yml`**](.github/workflows/release.yml): Packages and publishes both standalone Windows `.exe` bundles and `.bat` source archives when a version tag (e.g., `v2.0.0`) is published or triggered via workflow dispatch.

* [**`dependabot.yml`**](.github/dependabot.yml): Schedules regular dependency audits and automatic PR creation for security patches.


## 📂 Project Structure

```
ClipHaven/
├── .github/
│   ├── dependabot.yml            # Dependency updater configuration
│   └── workflows/
│       ├── ci.yml                # Multi-platform CI testing pipeline
│       └── release.yml           # Automated GitHub Releases builder (Full ZIP, Standalone .exe & Source ZIP)
├── tests/
│   └── test_server.py            # Unit and API integration test suite
├── logo.svg                      # Vector application logo and favicon
├── index.html                    # Clean, responsive web UI
├── style.css                     # Dark and light mode design tokens
├── app.js                        # Client state, preview rendering & polling
├── server.py                     # Local HTTP server and yt-dlp backend bridge
├── setup-and-run.bat             # Windows one-click runner and environment builder
├── requirements.txt              # Core Python dependencies (yt-dlp + imageio-ffmpeg)
├── pyproject.toml                # Project configurations and metadata
├── CHANGELOG.md                  # Detailed record of updates and version changes
└── LICENSE                       # MIT Open Source License
```

## 🤝 Contributing & Feedback

Contributions, suggestions, and bug reports are welcome!

* 🐛 **Found a bug?** Open an [Issue](https://github.com/AsadullahAlMunib/ClipHaven/issues).

* 💡 **Have a feature idea?** Start a discussion or submit a Pull Request.

* 📜 **Want to see what changed?** Check out the [CHANGELOG.md](CHANGELOG.md) or review the [Latest Release Notes](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest).


## 📄 License

This project is licensed under the [MIT License](LICENSE) — free for personal and commercial use.
