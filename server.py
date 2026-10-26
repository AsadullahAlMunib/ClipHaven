#!/usr/bin/env python3
"""Local-only backend for ClipHaven Video & Audio Downloader (v2.0.0)."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import threading
import subprocess
import sys
import os
import json
import uuid
import re
import time
import webbrowser
import logging

try:
    import tkinter as tk
    from tkinter import filedialog
except Exception:
    tk = None
    filedialog = None

VERSION = "2.0.0"

# Support both normal Python execution (setup-and-run.bat) and PyInstaller standalone .exe
IS_FROZEN = getattr(sys, "frozen", False)
BUNDLE_DIR = (
    Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    if IS_FROZEN
    else Path(__file__).resolve().parent
)
APP_DIR = (
    Path(sys.executable).resolve().parent
    if IS_FROZEN
    else Path(__file__).resolve().parent
)
ROOT = BUNDLE_DIR
HTML_FILE = BUNDLE_DIR / "index.html"


def get_ytdlp_cmd() -> list[str]:
    """Return the command prefix to invoke yt-dlp in both script and frozen .exe modes."""
    if IS_FROZEN:
        return [sys.executable, "--run-ytdlp"]
    return [sys.executable, "-m", "yt_dlp"]


def get_default_folder() -> Path:
    """Return a sensible default download folder that works even without a D: drive."""
    d_drive = Path("D:/")
    if os.name == "nt" and d_drive.exists():
        return Path(r"D:\Videos\Downloads")
    for candidate in (
        Path.home() / "Downloads" / "ClipHaven",
        Path.home() / "Videos" / "ClipHaven",
        Path.home() / "Downloads",
    ):
        try:
            if candidate.parent.exists():
                return candidate
        except Exception:
            continue
    return APP_DIR / "downloads"


DEFAULT_FOLDER = get_default_folder()

logging.basicConfig(
    filename=str(APP_DIR / "app.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

ALLOWED = {
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "facebook.com",
    "fb.watch",
    "fb.com",
    "fb.gg",
    "instagram.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "reddit.com",
    "redd.it",
    "vimeo.com",
    "dailymotion.com",
    "dai.ly",
    "twitch.tv",
}

VALID_FORMATS = {"mp4", "mkv", "webm", "mp3", "m4a", "wav"}
VALID_QUALITIES = {"best", "2160", "1440", "1080", "720", "480", "360"}
VALID_BROWSERS = {"", "none", "chrome", "edge", "firefox", "brave", "opera"}
MAX_JOBS = 40

lock = threading.Lock()
jobs = {}
procs = {}


def extract_url(raw: str) -> str:
    """Extract the first https:// URL if the user pasted extra share text around the link."""
    if not raw:
        return ""
    s = str(raw).strip()
    m = re.search(r"https?://[^\s<>\"']+", s)
    if m:
        return m.group(0).rstrip(".,;)!]>")
    return s


def valid_url(raw: str) -> bool:
    """Validate that the input contains an HTTPS URL from a supported platform."""
    url = extract_url(raw)
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme != "https" or not p.hostname:
        return False
    host = p.hostname.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in ALLOWED)


def validate_folder(folder) -> Path | None:
    """Validate and create the target save folder, rejecting drive roots."""
    if not folder or not str(folder).strip():
        return None
    raw = str(folder).strip()
    if re.match(r"^[a-zA-Z]:[\\/]*$", raw) or raw in {"/", "\\"}:
        return None
    try:
        p = Path(raw).expanduser()
        resolved = p.resolve()
        blocked = {Path.home().anchor, "C:\\", "D:\\", "/"}
        if str(resolved).lower().rstrip("\\/") in {
            str(x).lower().rstrip("\\/") for x in blocked if x
        }:
            return None
        p.mkdir(parents=True, exist_ok=True)
        if not p.is_dir():
            return None
        return p
    except Exception:
        return None


def parse_timestamp(ts: str) -> int | None:
    """Parse MM:SS or HH:MM:SS or seconds into total seconds. Returns None if invalid."""
    if not ts or not str(ts).strip():
        return None
    s = str(ts).strip()
    if not re.match(r"^\d{1,3}(:\d{1,2}){0,2}$", s):
        return None
    parts = [int(x) for x in s.split(":")]
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        if parts[1] >= 60:
            return None
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        if parts[1] >= 60 or parts[2] >= 60:
            return None
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None


def format_seconds(sec: int) -> str:
    """Format seconds as HH:MM:SS or MM:SS."""
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def ffmpeg_available() -> bool:
    """Check whether ffmpeg is available on PATH, next to the executable, or in Winget packages."""
    local_ffmpeg = APP_DIR / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if local_ffmpeg.is_file():
        os.environ["PATH"] = str(APP_DIR) + os.pathsep + os.environ.get("PATH", "")
        return True
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except Exception:
        if os.name == "nt":
            winget_pkgs = (
                Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
            )
            if winget_pkgs.exists():
                for exe in winget_pkgs.rglob("ffmpeg.exe"):
                    os.environ["PATH"] = (
                        str(exe.parent) + os.pathsep + os.environ.get("PATH", "")
                    )
                    return True
        return False


def terminate_process_tree(proc: subprocess.Popen):
    """Terminate a process and all its child processes (including ffmpeg)."""
    if not proc:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            proc.terminate()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def cleanup_partial_files(folder: Path, started_at: float):
    """Remove leftover .part and .ytdl files created during a cancelled job."""
    try:
        for pattern in ("*.part*", "*.ytdl", "*.temp*"):
            for f in folder.glob(pattern):
                try:
                    if f.stat().st_mtime >= started_at - 5:
                        f.unlink(missing_ok=True)
                except Exception:
                    pass
    except Exception:
        pass


def update(jid: str, **kwargs):
    """Thread-safe update of a job's state dictionary."""
    with lock:
        if jid in jobs:
            jobs[jid].update(kwargs)
            jobs[jid]["updated_at"] = time.time()


def prune_jobs():
    """Keep the in-memory jobs dictionary bounded to prevent memory leaks."""
    with lock:
        if len(jobs) <= MAX_JOBS:
            return
        finished = [
            (k, v.get("created_at", 0))
            for k, v in jobs.items()
            if v.get("state") in {"Complete", "Error", "Cancelled"}
        ]
        finished.sort(key=lambda x: x[1])
        while len(jobs) > MAX_JOBS and finished:
            oldest_id, _ = finished.pop(0)
            jobs.pop(oldest_id, None)


def fetch_video_info(url: str, cookies_browser: str = "") -> dict:
    """Fetch basic metadata (title, thumbnail, uploader, duration) using yt-dlp."""
    clean_url = extract_url(url)
    if not valid_url(clean_url):
        raise ValueError(
            "Enter a valid HTTPS video URL (YouTube, Facebook, Instagram, TikTok, etc.)."
        )
    cmd = get_ytdlp_cmd() + [
        "--dump-single-json",
        "--flat-playlist",
        "--no-warnings",
    ]
    if cookies_browser and cookies_browser not in {"none", ""}:
        cmd.extend(["--cookies-from-browser", cookies_browser])
    cmd.extend(["--", clean_url])
    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=25,
        cwd=str(APP_DIR),
    )
    if res.returncode != 0 or not res.stdout.strip():
        err_lines = [line.strip() for line in res.stderr.splitlines() if line.strip()]
        err_msg = next(
            (x for x in reversed(err_lines) if "ERROR:" in x),
            err_lines[-1] if err_lines else "Could not fetch video details.",
        )
        raise RuntimeError(err_msg.replace("ERROR:", "").strip()[:300])

    data = json.loads(res.stdout.splitlines()[-1])
    is_playlist = data.get("_type") == "playlist" or bool(data.get("entries"))
    entries = data.get("entries") or []
    duration = data.get("duration")
    duration_str = (
        format_seconds(int(duration))
        if isinstance(duration, (int, float)) and duration > 0
        else ""
    )

    thumbnail = data.get("thumbnail") or ""
    if not thumbnail and data.get("thumbnails"):
        thumbnail = data["thumbnails"][-1].get("url", "")
    if not thumbnail and is_playlist and entries:
        first_entry = entries[0] or {}
        thumbnail = first_entry.get("thumbnail") or ""
        if not thumbnail and first_entry.get("thumbnails"):
            thumbnail = first_entry["thumbnails"][-1].get("url", "")

    return {
        "title": data.get("title") or "Untitled video",
        "uploader": data.get("uploader")
        or data.get("channel")
        or data.get("extractor_key")
        or "Video",
        "duration": duration_str,
        "duration_seconds": int(duration) if isinstance(duration, (int, float)) else 0,
        "thumbnail": thumbnail,
        "is_playlist": is_playlist,
        "playlist_count": len(entries) if is_playlist else 1,
        "webpage_url": data.get("webpage_url") or clean_url,
    }


def download(
    jid: str,
    url: str,
    folder: str,
    quality: str,
    fmt_choice: str,
    start_time: str = "",
    end_time: str = "",
    subtitles: bool = False,
    embed_thumbnail: bool = False,
    allow_playlist: bool = False,
    cookies_browser: str = "",
):
    proc = None
    started_at = time.time()
    out = None
    try:
        out = validate_folder(folder)
        if out is None:
            raise ValueError("Invalid or inaccessible save folder.")
        clean_url = extract_url(url)
        logging.info("Starting download [%s] %s", jid, clean_url)

        has_ffmpeg = ffmpeg_available()
        playlist_flag = "--yes-playlist" if allow_playlist else "--no-playlist"
        output_template = str(out / "%(title).180B [%(id)s].%(ext)s")

        cmd = get_ytdlp_cmd() + [
            playlist_flag,
            "--newline",
            "--progress",
            "--windows-filenames",
        ]

        if fmt_choice in {"mp3", "m4a", "wav"}:
            if not has_ffmpeg and fmt_choice in {"mp3", "wav"}:
                raise RuntimeError(
                    f"FFmpeg is required to convert audio to {fmt_choice.upper()}. Please install FFmpeg or choose M4A / MP4."
                )
            cmd.extend(["-x", "--audio-format", fmt_choice, "--audio-quality", "0"])
        else:
            if has_ffmpeg:
                fmt = (
                    "bv*+ba/b"
                    if quality == "best"
                    else f"bv*[height<={quality}]+ba/b[height<={quality}]/b"
                )
                cmd.extend(["--format", fmt, "--merge-output-format", fmt_choice])
            else:
                # Graceful fallback to pre-merged single-file stream when FFmpeg is absent
                fmt = "b" if quality == "best" else f"b[height<={quality}]/b"
                cmd.extend(["--format", fmt])

        # Optional time trimming (Clip Trimmer)
        if start_time or end_time:
            if not has_ffmpeg:
                raise RuntimeError(
                    "FFmpeg is required for cutting/trimming video clips. Please install FFmpeg first."
                )
            s_sec = parse_timestamp(start_time) if start_time else 0
            e_sec = parse_timestamp(end_time) if end_time else None
            if s_sec is None or (end_time and e_sec is None):
                raise ValueError("Invalid clip time format. Use MM:SS or HH:MM:SS.")
            if e_sec is not None and e_sec <= s_sec:
                raise ValueError("End time must be greater than start time.")
            sec_range = f"*{s_sec}-{e_sec if e_sec is not None else 'inf'}"
            cmd.extend(["--download-sections", sec_range, "--force-keyframes-at-cuts"])

        # Optional subtitles
        if subtitles:
            cmd.extend(["--write-subs", "--write-auto-subs", "--sub-langs", "en.*,bn.*"])
            if fmt_choice in {"mp4", "mkv", "webm"} and has_ffmpeg:
                cmd.append("--embed-subs")

        # Optional thumbnail embedding
        if embed_thumbnail and has_ffmpeg:
            cmd.append("--embed-thumbnail")

        # Optional browser cookies for private/logged-in videos
        if cookies_browser and cookies_browser not in {"none", ""}:
            cmd.extend(["--cookies-from-browser", cookies_browser])

        cmd.extend(["--output", output_template, "--", clean_url])

        update(
            jid,
            state="Downloading",
            title="Starting download",
            detail="Connecting to video stream…",
            percent=0,
            speed="",
            eta="",
            stage="Preparing",
        )

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(APP_DIR),
            bufsize=1,
        )
        with lock:
            procs[jid] = proc

        recent = []
        saved_file = ""
        stream_count = 0

        for raw in proc.stdout:
            with lock:
                job_state = jobs.get(jid, {}).get("state")
            if job_state == "Cancelled":
                terminate_process_tree(proc)
                break

            line = raw.strip()
            if not line:
                continue
            recent.append(line)
            recent = recent[-15:]

            # Detect destination or merged file path
            dest_match = re.search(r"\[download\] Destination:\s+(.+)$", line)
            if dest_match:
                saved_file = dest_match.group(1).strip().strip('"')
                stream_count += 1

            merge_match = re.search(r'\[Merger\] Merging formats into "(.+?)"', line)
            if merge_match:
                saved_file = merge_match.group(1).strip()

            audio_match = re.search(r"\[ExtractAudio\] Destination:\s+(.+)$", line)
            if audio_match:
                saved_file = audio_match.group(1).strip().strip('"')

            already_match = re.search(
                r"\[download\]\s+(.+?)\s+has already been downloaded", line
            )
            if already_match:
                saved_file = already_match.group(1).strip().strip('"')

            # Parse download percentage, speed, and ETA
            prog_match = re.search(
                r"\[download\]\s+([\d.]+)%(?:\s+of\s+~?[\d.]+\w+)?(?:\s+at\s+([\d.]+\s*\w+/s))?(?:\s+ETA\s+([\d:]+))?",
                line,
            )
            kwargs = {"detail": line[:600]}
            if prog_match:
                pct = float(prog_match.group(1))
                kwargs["percent"] = pct
                kwargs["speed"] = (prog_match.group(2) or "").strip()
                kwargs["eta"] = (prog_match.group(3) or "").strip()
                if fmt_choice in {"mp3", "m4a", "wav"}:
                    kwargs["stage"] = "Downloading audio"
                    kwargs["title"] = f"Downloading audio ({pct:.0f}%)"
                elif stream_count <= 1:
                    kwargs["stage"] = "Downloading video"
                    kwargs["title"] = f"Downloading video ({pct:.0f}%)"
                else:
                    kwargs["stage"] = "Downloading audio track"
                    kwargs["title"] = f"Downloading audio track ({pct:.0f}%)"

            if "Merging formats" in line or "[Merger]" in line:
                kwargs["title"] = "Merging video & audio (almost done)…"
                kwargs["stage"] = "Merging"
                kwargs["speed"] = ""
                kwargs["eta"] = ""
            elif "[ExtractAudio]" in line:
                kwargs["title"] = "Converting audio format…"
                kwargs["stage"] = "Converting audio"
                kwargs["speed"] = ""
                kwargs["eta"] = ""
            elif "[EmbedThumbnail]" in line or "[EmbedSubtitle]" in line:
                kwargs["title"] = "Embedding metadata…"
                kwargs["stage"] = "Finalizing"

            if saved_file:
                kwargs["file_path"] = saved_file

            update(jid, **kwargs)

        rc = proc.wait()
        with lock:
            procs.pop(jid, None)
            job_state = jobs.get(jid, {}).get("state")

        if job_state == "Cancelled":
            cleanup_partial_files(out, started_at)
            update(
                jid,
                state="Cancelled",
                title="Download cancelled",
                detail="Download cancelled and temporary files cleaned up.",
                percent=0,
                speed="",
                eta="",
                stage="Cancelled",
            )
            return

        if rc == 0:
            final_name = Path(saved_file).name if saved_file else ""
            if final_name and not jobs.get(jid, {}).get("video_title_locked"):
                clean_title = re.sub(
                    r"\s*\[[A-Za-z0-9_-]{6,}\]\.[A-Za-z0-9]+$", "", final_name
                )
                if clean_title:
                    update(jid, video_title=clean_title)
            detail_msg = f"Saved: {final_name}" if final_name else f"Saved to: {out}"
            update(
                jid,
                state="Complete",
                title="Download complete!",
                detail=detail_msg,
                percent=100,
                speed="",
                eta="",
                stage="Complete",
                folder=str(out),
                file_path=saved_file or str(out),
            )
        else:
            raw_err = next(
                (x for x in reversed(recent) if "ERROR:" in x),
                recent[-1] if recent else "Download failed.",
            )
            friendly = friendly_error_message(raw_err)
            update(
                jid,
                state="Error",
                title="Download failed",
                detail=friendly[:600],
                percent=0,
                speed="",
                eta="",
                stage="Error",
            )
    except Exception as e:
        with lock:
            procs.pop(jid, None)
        update(
            jid,
            state="Error",
            title="Download failed",
            detail=str(e)[:600],
            percent=0,
            speed="",
            eta="",
            stage="Error",
        )
    finally:
        prune_jobs()


def friendly_error_message(raw_err: str) -> str:
    """Translate technical yt-dlp errors into clear, actionable advice for users."""
    clean = raw_err.replace("ERROR:", "").strip()
    lower = clean.lower()
    if "ffmpeg" in lower and ("not found" in lower or "installed" in lower):
        return f"{clean} — Tip: Install FFmpeg or choose a lower quality/standard MP4 format."
    if (
        "private video" in lower
        or "login" in lower
        or "sign in" in lower
        or "cookies" in lower
    ):
        return f"{clean} — Tip: Open 'Cut Clip / Extra Options' below and select your browser under 'Use Browser Login' to download private or age-restricted videos."
    if "unsupported url" in lower:
        return "This link is not supported or is not a direct video link. Please paste a valid video URL."
    return clean


def open_in_explorer(target_path: str) -> bool:
    """Open the given file or folder in the user's OS file manager."""
    if not target_path:
        return False
    p = Path(target_path).expanduser()
    if not p.exists():
        if p.parent.exists():
            p = p.parent
        else:
            return False
    try:
        if os.name == "nt":
            if p.is_file():
                subprocess.Popen(["explorer", f"/select,{str(p.resolve())}"])
            else:
                os.startfile(str(p.resolve()))
        elif sys.platform == "darwin":
            if p.is_file():
                subprocess.Popen(["open", "-R", str(p.resolve())])
            else:
                subprocess.Popen(["open", str(p.resolve())])
        else:
            subprocess.Popen(["xdg-open", str(p.parent if p.is_file() else p.resolve())])
        return True
    except Exception:
        return False


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BUNDLE_DIR), **kwargs)

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def json(self, code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/":
            self.path = "/index.html"
            return super().do_GET()
        if p.path in {"/style.css", "/app.js"}:
            return super().do_GET()
        if p.path == "/api/config":
            with lock:
                recent_list = sorted(
                    [{"id": k, **v} for k, v in jobs.items()],
                    key=lambda x: x.get("created_at", 0),
                    reverse=True,
                )[:10]
            return self.json(
                200,
                {
                    "ok": True,
                    "version": VERSION,
                    "default_folder": str(DEFAULT_FOLDER),
                    "ffmpeg": ffmpeg_available(),
                    "jobs": recent_list,
                },
            )
        if p.path == "/api/ffmpeg":
            return self.json(200, {"ok": True, "available": ffmpeg_available()})
        if p.path == "/api/status":
            jid = parse_qs(p.query).get("id", [""])[0]
            with lock:
                data = dict(jobs[jid]) if jid in jobs else None
            if not data:
                return self.json(404, {"ok": False, "error": "Download job not found."})
            data["ok"] = True
            return self.json(200, data)
        return self.json(404, {"ok": False, "error": "Not found."})

    def do_POST(self):
        origin = self.headers.get("Origin", "")
        if origin and not (
            origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:")
        ):
            return self.json(403, {"ok": False, "error": "Request origin not allowed."})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n > 20000:
                return self.json(413, {"ok": False, "error": "Request too large."})
            raw_body = self.rfile.read(n).decode("utf-8") if n > 0 else "{}"
            body = json.loads(raw_body or "{}")
        except Exception:
            return self.json(400, {"ok": False, "error": "Invalid request."})

        if self.path == "/api/choose-folder":
            if tk is None or filedialog is None:
                return self.json(
                    500,
                    {
                        "ok": False,
                        "error": "Folder picker is unavailable in this Python environment.",
                    },
                )
            result = {}

            def pick_folder():
                try:
                    root = tk.Tk()
                    root.withdraw()
                    root.attributes("-topmost", True)
                    initial = str(
                        DEFAULT_FOLDER if DEFAULT_FOLDER.exists() else Path.home()
                    )
                    folder = filedialog.askdirectory(
                        title="Choose video download folder", initialdir=initial
                    )
                    root.destroy()
                    result["folder"] = folder or ""
                except Exception as e:
                    result["error"] = str(e)

            t = threading.Thread(target=pick_folder, daemon=True)
            t.start()
            t.join(timeout=60)
            if "error" in result:
                return self.json(
                    500, {"ok": False, "error": f"Folder picker failed: {result['error']}"}
                )
            return self.json(200, {"ok": True, "folder": result.get("folder", "")})

        if self.path == "/api/info":
            url = extract_url(str(body.get("url", "")))
            cookies_browser = str(body.get("cookies_browser", "")).lower().strip()
            if not valid_url(url):
                return self.json(
                    400,
                    {
                        "ok": False,
                        "error": "Enter a valid HTTPS link (YouTube, Facebook, Instagram, TikTok, X, etc.).",
                    },
                )
            try:
                info = fetch_video_info(url, cookies_browser=cookies_browser)
                return self.json(200, {"ok": True, "info": info})
            except Exception as e:
                return self.json(400, {"ok": False, "error": str(e)})

        if self.path == "/api/download":
            url = extract_url(str(body.get("url", "")))
            folder = str(body.get("folder", str(DEFAULT_FOLDER))).strip()
            if not folder:
                return self.json(400, {"ok": False, "error": "Choose a save folder."})
            validated_folder = validate_folder(folder)
            if not validated_folder:
                return self.json(
                    400,
                    {
                        "ok": False,
                        "error": "Invalid save folder. Please choose an accessible folder.",
                    },
                )
            if not valid_url(url):
                return self.json(
                    400,
                    {
                        "ok": False,
                        "error": "Enter a valid HTTPS link (YouTube, Facebook, Instagram, TikTok, X, etc.).",
                    },
                )
            fmt_choice = str(body.get("format", "mp4")).lower().strip()
            if fmt_choice not in VALID_FORMATS:
                return self.json(400, {"ok": False, "error": "Choose a valid format."})
            quality = str(body.get("quality", "best")).strip()
            if fmt_choice in {"mp4", "mkv", "webm"} and quality not in VALID_QUALITIES:
                return self.json(400, {"ok": False, "error": "Choose a valid quality."})

            start_time = str(body.get("start_time", "")).strip()
            end_time = str(body.get("end_time", "")).strip()
            if start_time and parse_timestamp(start_time) is None:
                return self.json(
                    400,
                    {
                        "ok": False,
                        "error": "Start time must be in MM:SS or HH:MM:SS format (e.g. 01:20).",
                    },
                )
            if end_time and parse_timestamp(end_time) is None:
                return self.json(
                    400,
                    {
                        "ok": False,
                        "error": "End time must be in MM:SS or HH:MM:SS format (e.g. 03:45).",
                    },
                )
            if (
                start_time
                and end_time
                and parse_timestamp(end_time) <= parse_timestamp(start_time)
            ):
                return self.json(
                    400, {"ok": False, "error": "End time must be after start time."}
                )

            subtitles = bool(body.get("subtitles", False))
            embed_thumbnail = bool(body.get("embed_thumbnail", False))
            allow_playlist = bool(body.get("allow_playlist", False))
            cookies_browser = str(body.get("cookies_browser", "")).lower().strip()
            if cookies_browser not in VALID_BROWSERS:
                return self.json(
                    400, {"ok": False, "error": "Unsupported browser choice for cookies."}
                )

            raw_hint = str(body.get("title_hint", "")).strip()
            title_hint = raw_hint or "Video download"

            jid = uuid.uuid4().hex
            now = time.time()
            with lock:
                jobs[jid] = {
                    "state": "Queued",
                    "title": "Download queued",
                    "video_title": title_hint,
                    "video_title_locked": bool(raw_hint),
                    "url": url,
                    "format": fmt_choice.upper(),
                    "quality": "Audio"
                    if fmt_choice in {"mp3", "m4a", "wav"}
                    else ("Best" if quality == "best" else f"{quality}p"),
                    "detail": "Waiting to start…",
                    "percent": 0,
                    "speed": "",
                    "eta": "",
                    "stage": "Queued",
                    "folder": str(validated_folder),
                    "file_path": str(validated_folder),
                    "created_at": now,
                    "updated_at": now,
                }
            threading.Thread(
                target=download,
                args=(
                    jid,
                    url,
                    str(validated_folder),
                    quality,
                    fmt_choice,
                    start_time,
                    end_time,
                    subtitles,
                    embed_thumbnail,
                    allow_playlist,
                    cookies_browser,
                ),
                daemon=True,
            ).start()
            return self.json(
                202, {"ok": True, "id": jid, "folder": str(validated_folder)}
            )

        if self.path == "/api/cancel":
            jid = str(body.get("id", "")).strip()
            with lock:
                if jid in jobs:
                    jobs[jid]["state"] = "Cancelled"
                proc = procs.get(jid)
            if proc:
                terminate_process_tree(proc)
            return self.json(200, {"ok": True})

        if self.path == "/api/open-folder":
            target = str(body.get("path", "")).strip()
            jid = str(body.get("id", "")).strip()
            if not target and jid:
                with lock:
                    job = jobs.get(jid, {})
                    target = job.get("file_path") or job.get("folder") or ""
            if not target:
                target = str(DEFAULT_FOLDER)
            ok = open_in_explorer(target)
            if not ok:
                return self.json(
                    400, {"ok": False, "error": "Could not open folder on this system."}
                )
            return self.json(200, {"ok": True})

        if self.path == "/api/ffmpeg":
            return self.json(200, {"ok": True, "available": ffmpeg_available()})

        return self.json(404, {"ok": False, "error": "Not found."})


def main():
    # When invoked as `ClipHaven.exe --run-ytdlp <args>`, delegate directly to yt_dlp
    if len(sys.argv) > 1 and sys.argv[1] == "--run-ytdlp":
        import yt_dlp

        sys.argv = ["yt-dlp"] + sys.argv[2:]
        yt_dlp.main()
        return

    if not HTML_FILE.exists():
        raise SystemExit(f"Missing HTML file: {HTML_FILE}")

    server = None
    bound_port = None
    for port in range(8765, 8776):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            bound_port = port
            break
        except OSError:
            continue

    if server is None or bound_port is None:
        print("Error: Could not bind to any port between 8765 and 8775.")
        sys.exit(1)

    url = f"http://127.0.0.1:{bound_port}/"
    print(f"ClipHaven v{VERSION} — Catch, keep, and enjoy your clips. Running at {url}")
    print("Keep this window open while downloading. Press Ctrl+C to stop the app.")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
