# Changelog

All notable changes to **ClipHaven** are documented in this file.


## [[3.2.0](https://github.com/AsadullahAlMunib/ClipHaven/releases/tag/v3.2.0)] - 2026-10-30

### Added & Improved
- **In-App Update Checker & Android Auto-Updater (`FileProvider` + Release Notes Modal)**: Automatically checks GitHub Releases on startup (with 4-hour caching to prevent rate limits), displays an interactive update popup with expandable release notes, and on Android downloads the architecture-matched `.apk` in the background and launches the native package installer directly.
- **YouTube SABR & GVS PO Token Bypass (`player_client=android,web,default`)**: Switched primary extraction client to Android (`android,web,default`), completely bypassing YouTube's experimental SABR stream blocks on iOS and GVS PO Token requirements on mweb.
- **Direct Device Folder Picker on Android**: Eliminated confusing intermediate selection dialogs—tapping `📁 Browse` now directly opens the native device folder picker (SAF), grants persistent tree permissions, supports SD cards, and seamlessly writes to any chosen directory via DocumentsContract.
- **Android Package Identifier Renamed**: Updated package name and application ID to `com.asadullahalmunib.cliphaven` across Gradle build configurations, manifest, ProGuard rules, action intents, and directory structure.
- **Auto-Default Playlist Download & Interactive Video Selector Dropdown (`--playlist-items`)**: Automatically enables full playlist download when a playlist link is pasted and displays a collapsible dropdown listing all videos in the playlist with checkboxes (`✅ Select All` / `🎬 Single Video Only` / custom video selection).
- **Instant Sub-Second Video Previews (`oEmbed` + Direct Thumbnail + In-Memory Cache)**: Added lightweight `oEmbed` metadata resolution (~0.2s) for YouTube, TikTok, Vimeo, Dailymotion, SoundCloud, and Reddit alongside instant client-side YouTube thumbnail rendering and a 64-entry LRU preview cache, reducing preview load times from 1.5–2 minutes to under 1 second.
- **High-Speed Downloads & Clip Cutting (`--force-ipv4`, `--concurrent-fragments 4`, `-preset ultrafast`)**: Forced IPv4 routing (`-4`) to eliminate 25-second IPv6 blackhole timeouts, enabled 4-thread parallel DASH/HLS fragment downloads, used in-process `yt_dlp` on Desktop to avoid cold subprocess spawns, made Android engine updates non-blocking on startup/preview, and added `-preset ultrafast` for 3x–5x faster video clip cutting.
- **LinkedIn Video & Post Support**: Added native URL validation and extraction support for `linkedin.com` and `lnkd.in` share links across Desktop and Android.
- **YouTube-Style Native Original CC (`.*-orig,bn,en` + `skip=translated_subs`)**: Automatically embeds the exact original language spoken in the video (`.*-orig` — whether Bangla, English, Hindi, Arabic, or any other language) and skips robotic machine-translated subtitle tracks (`skip=translated_subs`), matching YouTube's native CC button behavior.
- **Android Background Downloads & Foreground Service**: Added `DownloadForegroundService` with live notification progress, `PARTIAL_WAKE_LOCK`, and Android 14 `dataSync` foreground service type so downloads and video conversions continue reliably when the screen turns off or the app is minimized.
- **Double Storage Elimination & Incremental Playlist Export**: Completed files are moved out of internal cache immediately upon completion, and playlist items are exported incrementally to `Downloads/ClipHaven` rather than waiting for the entire playlist to finish.
- **Mobile Connection Resilience**: Added `--retries 10`, `--fragment-retries 10`, `--file-access-retries 5`, and `--socket-timeout 30` to prevent mobile network dropouts or signal fluctuations from killing downloads.
- **Back Button Navigation Protection**: Added `OnBackPressedCallback` in `MainActivity` to minimize to background (`moveTaskToBack(true)`) during active downloads instead of terminating the app and cancelling progress.
- **Battery & CPU Optimization**: Tuned subtitle sync watcher polling from 80ms to 400ms to reduce mobile CPU load and flash storage I/O wakeups.



## [[3.1.2](https://github.com/AsadullahAlMunib/ClipHaven/releases/tag/v3.1.2)] - 2026-10-30

### Fixed & Improved
- **Clipped Video Subtitle Sync & Time-Shifting**: Automatically trims `.vtt`/`.srt` subtitle cues (including inline word-level auto-caption timestamps) to the exact `[Start Time, End Time]` clip window and shifts all timestamps back by `-Start Time` so subtitles start at `00:00` in sync with the cut video.
- **Exact Clipped Container Duration**: Clamps boundary subtitle cues at the clip end timestamp, passes `--postprocessor-args "EmbedSubtitle+ffmpeg_o:-t <clip_duration>"`, and disables full-video chapter embedding (`--no-embed-chapters`) on clip jobs so embedded subtitle tracks never stretch the output `.mp4`/`.mkv`/`.webm` duration to the original full video length.


## [[3.1.1](https://github.com/AsadullahAlMunib/ClipHaven/releases/tag/v3.1.1)] - 2026-10-30

### Fixed & Improved
- **YouTube Bot & Sign-In Bypass**: Added `--extractor-args "youtube:player_client=default,ios,mweb"` across Android and Desktop to eliminate `Precondition check failed (HTTP 400)` and `Please sign in` bot attestation blocks.
- **Runtime yt-dlp Auto-Sync**: Added background `updateYoutubeDL` engine sync in Android to ensure mobile extraction stays continually updated with YouTube API changes.
- **Clean Storage Path Display**: Stripped the raw internal Linux `/storage/emulated/0/` prefix across the mobile UI, folder picker, and toast messages while keeping full desktop drive paths (`C:\...`, `D:\...`) untouched.
- **Dedicated 64-bit & 32-bit APK Builds**: Generated separate slim APKs (`ClipHaven-Android-64bit.apk` and `ClipHaven-Android-32bit.apk`) with disabled R8 minification to prevent native startup crashes.

## [[3.1.0](https://github.com/AsadullahAlMunib/ClipHaven/releases/tag/v3.1.0)] - 2026-10-29

### Android & Build Pipeline
- **Split 64-bit & 32-bit Slim APKs (~35 MB & ~32 MB)**: Replaced the 100+ MB universal APK with dedicated ABI-split builds (`ClipHaven-Android-64bit.apk` for modern 64-bit devices and `ClipHaven-Android-32bit.apk` for legacy 32-bit devices) while keeping R8 minification disabled so `youtubedl-android` runtime libraries never get stripped on launch.
- **Seamless Updates**: Added persistent release signing (`cliphaven-release.jks`) so future APKs update in place without reinstallation.
- **Clean Storage Path Display**: Replaced raw Linux `/storage/emulated/0/` with user-friendly `Internal Storage/` and `Downloads/` across the mobile UI and picker.
- **YouTube Anti-Bot & Sign-In Bypass**: Added `--extractor-args "youtube:player_client=default,ios,mweb"` and runtime `updateYoutubeDL` auto-sync to eliminate YouTube "Precondition check failed" and "Please sign in" errors.
- **Storage & Permissions**: Full Scoped Storage / MediaStore integration (`cacheDir` staging + `MediaStore.Downloads` fallback) for Android 11–14 and runtime permission support for Android 7–10.
- **Folder Picker & Gallery Sync**: Added SAF folder picker (`ACTION_OPEN_DOCUMENT_TREE`), safe custom subfolder path normalization, and instant `MediaScannerConnection` file indexing for Gallery/Music apps.
- **Engine Stability**: Mounted `WebView` first in `onCreate`, caught `Throwable` across all background threads/JNI calls, added synchronized Python/FFmpeg startup checks, and fixed mobile SSL handshake errors.

### Frontend & UX
- **Duplicate Job Guard**: Blocked accidental double submissions and orphaned downloads on `Enter` keypress.
- **Smart URL Parsing**: Auto-extracts clean media links from shared or pasted text across major social platforms.
- **Responsive UI States**: Clear preview error messages, format-aware toggle guards, and live playlist badge sync.

### Backend & Media Processing
- **Cover Art & Subtitles**: Fixed thumbnail/subtitle embedding for MP4, M4A, and MP3 using `mutagen`, `--convert-thumbnails jpg`, `--convert-subs srt`, and targeted language codes (`en,bn,en-orig`).
- **Live Trimming Progress**: Real-time progress, speed, and ETA calculation during clip cutting (`--downloader-args "ffmpeg:-stats -v warning"`).
- **Playlist & Concurrent Safety**: Accurate single-video playlist previews and stem-scoped cleanup for cancelled downloads.
- **Expanded Support**: Added native handling for `threads.com` and `snd.sc`.



## [[3.0.0](https://github.com/AsadullahAlMunib/ClipHaven/releases/tag/v3.0.0)] - 2026-10-29

### Added
- **Multi-Platform Release Suite (10 Automated Release Assets in `release.yml`)**:
  - **Windows**: `ClipHaven-Windows-All.zip` (Full `--onedir` bundle + `ffmpeg.exe`) & `ClipHaven-Windows.exe` (Standalone).
  - **macOS**: `ClipHaven-macOS-All.zip` (Full bundle + `ffmpeg`) & `ClipHaven-macOS` (Standalone).
  - **Linux x64**: `ClipHaven-Linux-x64-All.zip` (Full bundle + `ffmpeg`) & `ClipHaven-Linux-x64` (Standalone).
  - **Linux ARM64**: `ClipHaven-Linux-ARM64-All.zip` (Full bundle + `ffmpeg`) & `ClipHaven-Linux-ARM64` (Standalone).
  - **Android**: `ClipHaven-Android.apk` (Self-contained Android app in `android/` powered by `youtubedl-android` with embedded Python, `yt-dlp`, and `FFmpeg` running in private app data).
  - **Source**: `ClipHaven-Source-Bat.zip` (Lightweight source bundle with `setup-and-run.bat`).
- **Native OS Folder Picker (`📁 Browse` & `/api/pick-folder`)**: Added a `📁 Browse` button next to the Save Folder input that opens a native folder selection dialog on Windows, macOS, and Linux without requiring `tkinter`.
- **Live Playlist Progress Counter (`📑 X/Y • Done • Left`)**: Parses playlist item progress from `yt-dlp` and displays a live badge in the status bar showing current video index, total videos, completed count, and remaining count, while resetting stream counters per item.
- **Real-Time Clip Cutter Progress, Speed & ETA**: Added `--downloader-args "ffmpeg:-stats"` and FFmpeg `time=` / `speed=` parsing so trimming video clips (`Start Time` / `End Time`) displays live percentage progress (`0%–100%`), encoding speed, and remaining `ETA`, plus an animated indeterminate shimmer bar during post-processing stages (`Subtitles (CC)`, `Embedding cover`, `Merging`, `Converting audio`).
- **Smart Multi-Language Subtitles (`orig,bn.*,en.*`)**: Automatically downloads and embeds the video's original language alongside Bangla and English subtitles without triggering YouTube `HTTP 429` rate limits.
- **Pixel-Faithful `logo.svg` Icon Generator (`scripts/generate_icons.py`)**: Replaced the placeholder rectangle icon in `release.yml` with a high-resolution supersampled renderer that converts `logo.svg` into multi-size `logo.ico` and Android launcher icons.
- **Expanded Platform Domains**: Added support for `t.co` (X/Twitter mobile share links), `threads.net`, `pinterest.com`, `pin.it`, and `soundcloud.com`, plus automatic `https://` normalization for bare domain links and mid-text `http://` share links.
- **Interactive Download Dropdown in `README.md`**: Added an expandable `<details>` download selector at the top of `README.md` alongside the comparison table.

### Fixed
- **Windows Explorer File Highlight Fix (`open_in_explorer`)**: Passed `explorer.exe /select,"<path>"` with proper quoting so paths containing spaces highlight the downloaded file in its true folder instead of opening `Documents`.
- **FFmpeg Discovery Cache Fix (`get_ffmpeg_path`)**: Only caches `get_ffmpeg_path()` once a valid binary is found so installing FFmpeg while the server is running is detected immediately without restarting.
- **Preview Card Reset Fix (`hidePreview`)**: Reset `lastPreviewUrl = ""` inside `hidePreview()` so clearing the URL with the keyboard and re-pasting the same link always triggers the video preview card.
- **Social Media Thumbnail Loading (`referrerpolicy="no-referrer"`)**: Added `referrerpolicy="no-referrer"` and an `onerror` fallback on `#preview-thumb` so Instagram, Facebook, and TikTok CDN thumbnails load without `403 Forbidden` blocks.
- **Thumbnail Embedding Container Guard**: Skipped `--embed-thumbnail` when `WEBM` or `WAV` is selected so `yt-dlp` never fails at post-processing on unsupported containers.
- **Clip End-Time Endpoint Validation**: Validated `end_time <= start_time` even when `start_time` is omitted (`00:00`) directly in `/api/download`.
- **Page Refresh Completed Job Recovery**: Jobs that finish while the browser tab is refreshing are now recorded in `Recent Downloads` (`addToHistory`) and displayed in the status panel.
- **Windows Process Tree Cancellation & Stream Cleanup**: Used `taskkill /F /T /PID` on Windows to terminate child `ffmpeg.exe` processes on cancel and cleaned up unmerged `*.f[0-9]*.*` stream files.
- **Batch Launcher Fallback Quoting (`setup-and-run.bat`)**: Fixed `%RUN_PY%` quoting when `.venv` is absent and added a real Python 3.10+ version check.



## [[2.1.1](https://github.com/AsadullahAlMunib/ClipHaven/releases/tag/v2.1.1)] - 2026-10-28

### Added & Improved
- **Three Release Assets in GitHub Actions (`release.yml`)**:
  - `ClipHaven-Windows-EXE.zip` (**Recommended**): Full Windows `--onedir` app bundle with all dependencies and `ffmpeg.exe` pre-included for instant startup and minimal antivirus false positives.
  - `ClipHaven.exe`: Standalone single-file executable with embedded `ffmpeg.exe`.
  - `ClipHaven-Source-Bat.zip`: Lightweight source code bundle with `setup-and-run.bat`.
- **Cached FFmpeg Resolution (`@lru_cache`)**: Cached `get_ffmpeg_path()` in memory and auto-provisioned a standard `ffmpeg.exe` binary from `imageio-ffmpeg` on first run so `yt-dlp` never fails on non-standard binary names or repeated disk scans.
- **Clip Trimmer Filename Collision Fix**: Appended `[clip <start>_to_<end>]` to output filenames when `Start Time` or `End Time` is used, preventing `yt-dlp` from skipping clipped downloads when the full video already exists in the folder.
- **Fast Playlist Previews (`--playlist-end 50`)**: Capped playlist metadata scanning during link preview so large playlists load in 1–2 seconds instead of timing out.
- **Clean Child Process Termination & Memory Bounds**: Used process groups (`CREATE_NEW_PROCESS_GROUP` / `CTRL_BREAK_EVENT`) so cancelling a job cleanly terminates child `ffmpeg` processes and unlocks `.part` files, and re-added bounded job pruning (`MAX_JOBS = 40`).
- **Frontend Polling Retry Tolerance & HTTP-to-HTTPS Upgrade**: Added retry tolerance (up to 4 consecutive retries) in `app.js` status polling so brief hiccups do not abort progress tracking, and automatically upgraded `http://` links pasted in the UI to `https://`.
- **CI Linter Safety (`E402`)**: Updated `.github/workflows/ci.yml` to ignore
`E402` alongside `E501` for test path imports.



## [[2.1.0](https://github.com/AsadullahAlMunib/ClipHaven/releases/tag/v2.1.0)] - 2026-10-27

### Added
- **Custom SVG Brand Logo (`logo.svg`)**: Added vector logo and browser favicon, plus automated multi-resolution Windows `.ico` generation in GitHub Actions.
- **Automatic FFmpeg Bundling (`imageio-ffmpeg`)**: Included `imageio-ffmpeg` in `requirements.txt` and passed `--ffmpeg-location` automatically in `server.py`, eliminating missing FFmpeg errors for 1080p/4K merging, MP3/WAV conversion, and clip cutting.
- **Antivirus-Friendly GitHub Actions Release (`release.yml`)**:
  - Switched Windows `.exe` build from `--onefile` to `--onedir` with pre-bundled `ffmpeg.exe` (`ClipHaven-Windows-EXE.zip`) to eliminate PyInstaller temp-unpacking false positives in Windows Defender and Chrome Safe Browsing.
  - Separated `ClipHaven-Windows-EXE.zip` and `ClipHaven-Source-Bat.zip` so `.exe` and `.bat` files are never mixed in the same archive.

### Changed & Fixed
- **Streamlined `server.py` Codebase**: Reduced `server.py` from 945 lines to ~460 lines while keeping all core download, preview, clip trimming, subtitle, and thumbnail features intact.
- **Clean `setup-and-run.bat`**: Removed Windows Registry queries (`reg query HKLM\SYSTEM...`) and silent `winget` installs that triggered antivirus heuristic warnings and batch variable expansion bugs.
- **Removed Unnecessary Bloat**: Removed local `build-exe.bat`, Tkinter folder picker (`--exclude-module tkinter`), and browser cookie extraction to improve security and eliminate false-positive malware flags.



## [[2.0.0](https://github.com/AsadullahAlMunib/ClipHaven/releases/tag/v2.0.0)] - 2026-10-26

### Added
- **Dual Launch Architecture (`.exe` + `setup-and-run.bat`)**:
  - Added full PyInstaller frozen `.exe` support (`ClipHaven.exe`) so users without Python installed can run the app with a double-click.
  - Kept the classic `setup-and-run.bat` workflow so users can also run directly from source with automatic `.venv` and `yt-dlp` updates.
  - Added `build-exe.bat` for one-click local `.exe` compilation and `.github/workflows/release.yml` for automated GitHub Releases.
- **Auto Video Preview Card**: Automatically displays the video thumbnail, title, channel/uploader, duration, and playlist count as soon as a link is pasted.
- **One-Click Clipboard Paste & Clear**: Added `📋 Paste` and `✕` clear buttons to the URL field.
- **Multi-Platform Support**: Added support for Instagram, TikTok, X (Twitter), Reddit, Vimeo, Dailymotion, and Twitch alongside YouTube and Facebook.
- **Smart URL Extraction**: Automatically extracts the video URL even when pasted with surrounding share text from mobile apps.
- **4K & 2K Quality Options**: Added `2160p (4K)`, `1440p (2K)`, and `360p (Data Saver)` quality presets.
- **Live Speed, ETA & Stage Tracking**: Real-time download speed (`⚡ MB/s`), remaining time (`⏱ ETA`), and stage indicators (`Downloading video`, `Downloading audio track`, `Merging`).
- **One-Click Open Folder & Recent Downloads History**: Added `📂 Open Folder` button upon completion (highlights the file in Windows Explorer) and a persistent **Recent Downloads** list.
- **Collapsible Extra Options**:
  - **✂️ Cut Clip (Time Range)**: Download specific sections (`Start Time` to `End Time` in `MM:SS` or `HH:MM:SS`).
  - **Subtitles (CC)**: Download and embed English/Bangla subtitles.
  - **Embed Cover Art / Thumbnail**: Embed video thumbnail into downloaded media.
  - **Playlist Toggle**: Option to download an entire playlist or single video.
  - **Browser Login Cookies**: Support for Chrome, Edge, Firefox, Brave, and Opera cookies to download private or age-restricted videos.
- **GitHub Actions CI/CD & Dependabot**:
  - Upgraded `.github/workflows/ci.yml` with `ruff` linting, pip caching, and multi-OS (`windows-latest`, `ubuntu-latest`, `macos-latest`) + multi-Python (`3.10`, `3.11`, `3.12`) matrix testing.
  - Added `.github/workflows/release.yml` to automatically build and publish both `ClipHaven-Windows-EXE.zip` and `ClipHaven-Source-Bat.zip` to GitHub Releases.
  - Added `.github/dependabot.yml` for weekly dependency updates.

### Fixed
- **Cross-Drive Default Folder Fallback**: Automatically falls back to `Downloads\ClipHaven` when a `D:` drive is not present on the user's computer.
- **Batch Launcher (`setup-and-run.bat`)**: Fixed system Python command quoting crash (`"py -3"`) and added immediate Windows `PATH` refresh after installing FFmpeg via `winget`.
- **Clean Cancellation**: Terminates the entire child process tree (including `ffmpeg`) on cancel and cleans up leftover `.part` and `.ytdl` files.
- **Graceful FFmpeg Fallback**: Falls back to pre-merged video streams if FFmpeg is not installed, and displays a helpful banner at startup.
- **Session & Folder Persistence**: Remembers the user's chosen save folder in `localStorage` and automatically resumes progress tracking if the browser tab is refreshed mid-download.
- **Automatic Port Fallback**: Automatically binds to the next available port (`8765`–`8775`) if port `8765` is already in use.



## [[1.0.0](https://github.com/AsadullahAlMunib/ClipHaven/releases/tag/v1.0.0)] - Initial Release
- Local browser UI at `http://127.0.0.1:8765/` for YouTube and Facebook downloads.
- Basic format (`MP4`, `MKV`, `WEBM`, `MP3`, `M4A`, `WAV`) and quality (`best`, `1080p`, `720p`, `480p`) selection.
- Dark/light theme toggle and `setup-and-run.bat` launcher.
