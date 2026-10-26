# 🎬 ClipHaven

**Catch, keep, and enjoy your clips — locally, safely, and effortlessly.**

![CI Status](https://img.shields.io/badge/CI-passing-brightgreen)
![Release](https://img.shields.io/badge/version-v2.0.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)


[✨ Features](#-key-features) • [⚡ Quick Download](#-quick-downloads) • [🚀 Getting Started](#-getting-started) • [📖 How to Use](#-how-to-use) • [⚙️ Advanced Options](#-advanced-options) • [📦 Releases](https://github.com/AsadullahAlMunib/ClipHaven/releases)

ClipHaven is a modern, high-speed, 100% local video and audio downloader powered by [`yt-dlp`](https://github.com/yt-dlp/yt-dlp). It runs privately on your computer (`127.0.0.1:8765`) through a clean dark/light web UI—**no ads, no tracking, no external server relays, and zero telemetry**.

## ⚡ Quick Downloads

| Package | Recommended For | Direct Link | 
| ----- | ----- | ----- | 
| **🚀 Windows Standalone `.exe`** | Direct launch with **no Python required** | [⬇️ Download `ClipHaven-Windows-EXE.zip`](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest/download/ClipHaven-Windows-EXE.zip) | 
| **⚡ Hybrid Bundle (`.bat` + `.venv`)** | Auto-updating yt-dlp & script usage on Windows | [⬇️ Download `ClipHaven-Source-Bat.zip`](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest/download/ClipHaven-Source-Bat.zip) | 
| **🌐 Cross-Platform Source** | Linux, macOS, or custom developer environments | [📦 Viewl All Releases & Source Code](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest) | 

## ✨ Key Features

### 💻 Dual Launch Modes

* **Option A — Standalone Portable `.exe`:** Double-click and run immediately without installing Python or dependencies.

* **Option B — One-Click `setup-and-run.bat`:** Automatically creates a isolated `.venv`, upgrades `yt-dlp`, checks `FFmpeg`, and opens your default browser.

### 🌐 Wide Multi-Platform Extraction

Cleanly extracts video and audio from popular media platforms:

* **YouTube:** Full Videos, Shorts, and complete Playlists
* **Meta:** Facebook Videos & Reels, Instagram Reels & Posts
* **Others:** TikTok, X (Twitter), Reddit, Vimeo, Dailymotion, and Twitch

### 🎯 Precision Tools & Media Options

* **✂️ Video Trimming & Clip Cutter:** Download only the section you need by specifying `Start Time` and `End Time` (e.g., `01:15` to `02:30`).

* **🔐 Browser Cookie Authentication:** Extract cookies from **Chrome, Edge, Firefox, Brave, or Opera** to download private, member-only, or age-restricted videos you have access to.

* **📋 Smart URL Sanitizer:** Strips out messy share text and metadata from mobile app links automatically.

* **🖼️ Real-Time Metadata Previews:** Instantly inspect thumbnail, duration, title, and channel information before downloading.

* **📑 Playlist Downloads:** Download entire video playlists in batch with auto-detected item counts.

* **💬 Multi-Language Subtitles (CC):** Download and embed English or Bangla subtitles directly into your video files.

* **⚡ Multiple Formats & 4K Quality:**

  * **Video Formats:** `MP4` *(Recommended)*, `MKV`, `WEBM`

  * **Audio Formats:** `MP3`, `M4A`, `WAV` (automatically disables irrelevant video resolution selectors)

  * **Resolutions:** `Best Available`, `4K (2160p)`, `2K (1440p)`, `1080p`, `720p`, `480p`, `360p`

* **📊 Real-Time Feedback:** Live download speed counters (`MB/s`), accurate remaining time (`ETA`), percentage progress bars, and post-download directory navigation (`📂 Open Folder`).

## 🚀 Getting Started

### Method 1: Portable Executable (Windows)

1. Grab the latest release archive from [Releases](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest) or click [ClipHaven-Windows-EXE.zip](https://github.com/AsadullahAlMunib/ClipHaven/releases/latest/download/ClipHaven-Windows-EXE.zip).

2. Extract the archive into any folder.

3. Launch **`ClipHaven.exe`**. Your default browser will immediately open `http://127.0.0.1:8765/`.

### Method 2: One-Click Script (`setup-and-run.bat`)

1. Verify that **Python 3.10+** is installed with the **"Add Python to PATH"** checkbox selected during setup.

2. Clone or download this repository:

   ```
   git clone https://github.com/AsadullahAlMunib/ClipHaven.git
   cd ClipHaven
   
   ```

3. Double-click **`setup-and-run.bat`**. The script manages virtual environment creation, updates `yt-dlp`, checks `FFmpeg`, and opens the dashboard automatically.

### Method 3: Cross-Platform & Developer Setup (macOS / Linux / Windows)

```
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt pytest

# 3. Launch server
python server.py

# 4. (Optional) Run tests locally
pytest -v

```

## 📖 How to Use

```
  [ 1. Paste Link ]  --->  [ 2. Choose Format & Quality ]  --->  [ 3. Pick Save Folder ]  --->  [ 4. Click Download ]
          │                                                                                              │
          └───────────> Optional: Clip Trimming / Subtitles / Cookie Auth <──────────────────────────────┘

```

1. **Paste Link:** Paste any video URL into the input field or press **📋 Paste**. ClipHaven fetches metadata and displays the media preview.

2. **Choose Settings:** Select your target format (`MP4`, `MP3`, etc.) and quality preference.

3. **Select Folder:** Use the default download path or click **📁 Browse…** to define a custom destination.

4. **Extra Options *(Optional)*:**

   * Expand **⚙️ Cut Clip / Extra Options** to specify time bounds (`00:30` to `01:45`).

   * Toggle **Include Subtitles (CC)** or **Embed Cover Art**.

   * Select your daily browser to pass authorized login sessions for restricted videos.

5. **Download:** Hit **⬇ Download Now**. Monitor real-time status and click **📂 Open Folder** upon completion.

## 🏗️ Building `.exe` Locally

To build your own standalone single-file binary:

```
:: Run the included build script on Windows
build-exe.bat

```

The compiled binary will be placed inside `dist\ClipHaven.exe`.

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
│       └── release.yml           # Automated GitHub Releases builder
├── tests/
│   └── test_server.py            # Unit and API integration test suite
├── index.html                    # Clean, responsive web UI
├── style.css                     # Dark and light mode design tokens
├── app.js                        # Client state, preview rendering & polling
├── server.py                     # Local HTTP server and yt-dlp backend bridge
├── setup-and-run.bat             # Windows one-click runner and environment builder
├── build-exe.bat                 # PyInstaller packaging script
├── requirements.txt              # Core Python dependencies
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
