#!/usr/bin/env python3
"""Local-only backend for ClipHaven Video & Audio Downloader (v2.1.0)."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import threading
import subprocess
import shutil
import sys
import os
import json
import uuid
import re
import time
import webbrowser
import logging

VERSION = "2.1.0"
IS_FROZEN = getattr(sys, "frozen", False)
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) if IS_FROZEN else Path(__file__).resolve().parent
APP_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent
HTML_FILE = BUNDLE_DIR / "index.html"
DEFAULT_FOLDER = (Path.home() / "Downloads" / "ClipHaven") if (Path.home() / "Downloads").exists() else (APP_DIR / "downloads")

logging.basicConfig(filename=str(APP_DIR / "app.log"), level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ALLOWED = {
    "youtube.com", "youtu.be", "youtube-nocookie.com", "facebook.com", "fb.watch", "fb.com", "fb.gg",
    "instagram.com", "tiktok.com", "twitter.com", "x.com", "reddit.com", "redd.it", "vimeo.com", "dailymotion.com", "dai.ly", "twitch.tv",
}
VALID_FORMATS = {"mp4", "mkv", "webm", "mp3", "m4a", "wav"}
VALID_QUALITIES = {"best", "2160", "1440", "1080", "720", "480", "360"}

lock = threading.Lock()
jobs = {}
procs = {}


def get_ytdlp_cmd() -> list[str]:
    return [sys.executable, "--run-ytdlp"] if IS_FROZEN else [sys.executable, "-m", "yt_dlp"]


def get_ffmpeg_path() -> str | None:
    """Locate ffmpeg binary from app folder, system PATH, imageio-ffmpeg package, or WinGet."""
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    for base in (APP_DIR, BUNDLE_DIR):
        candidate = base / exe_name
        if candidate.is_file():
            return str(candidate)
    which_ff = shutil.which("ffmpeg")
    if which_ff:
        return which_ff
    try:
        import imageio_ffmpeg
        pkg_ff = imageio_ffmpeg.get_ffmpeg_exe()
        if pkg_ff and Path(pkg_ff).is_file():
            return str(pkg_ff)
    except Exception:
        pass
    if os.name == "nt":
        winget_pkgs = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
        if winget_pkgs.exists():
            for exe in winget_pkgs.rglob("ffmpeg.exe"):
                return str(exe)
    return None


def ffmpeg_available() -> bool:
    return get_ffmpeg_path() is not None


def extract_url(raw: str) -> str:
    if not raw:
        return ""
    s = str(raw).strip()
    m = re.search(r"https?://[^\s<>\"']+", s)
    return m.group(0).rstrip(".,;)!]>") if m else s


def valid_url(raw: str) -> bool:
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
    if not folder or not str(folder).strip():
        return None
    raw = str(folder).strip()
    if re.match(r"^[a-zA-Z]:[\\/]*$", raw) or raw in {"/", "\\"}:
        return None
    try:
        p = Path(raw).expanduser()
        resolved = str(p.resolve()).lower().rstrip("\\/")
        blocked = {str(x).lower().rstrip("\\/") for x in (Path.home().anchor, "C:\\", "D:\\", "/") if x}
        if resolved in blocked:
            return None
        p.mkdir(parents=True, exist_ok=True)
        return p if p.is_dir() else None
    except Exception:
        return None


def parse_timestamp(ts: str) -> int | None:
    if not ts or not str(ts).strip():
        return None
    s = str(ts).strip()
    if not re.match(r"^\d{1,3}(:\d{1,2}){0,2}$", s):
        return None
    parts = [int(x) for x in s.split(":")]
    if len(parts) == 2 and parts[1] < 60:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3 and parts[1] < 60 and parts[2] < 60:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return parts[0] if len(parts) == 1 else None


def format_seconds(sec: int) -> str:
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def terminate_process(proc: subprocess.Popen):
    if not proc:
        return
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def cleanup_partial_files(folder: Path, started_at: float):
    try:
        for pattern in ("*.part*", "*.ytdl", "*.temp*"):
            for f in folder.glob(pattern):
                if f.stat().st_mtime >= started_at - 5:
                    f.unlink(missing_ok=True)
    except Exception:
        pass


def update(jid: str, **kwargs):
    with lock:
        if jid in jobs:
            jobs[jid].update(kwargs, updated_at=time.time())


def fetch_video_info(url: str) -> dict:
    clean_url = extract_url(url)
    if not valid_url(clean_url):
        raise ValueError("Enter a valid HTTPS video URL (YouTube, Facebook, Instagram, TikTok, etc.).")
    cmd = get_ytdlp_cmd() + ["--dump-single-json", "--flat-playlist", "--no-warnings", "--", clean_url]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", timeout=25, cwd=str(APP_DIR))
    if res.returncode != 0 or not res.stdout.strip():
        err_lines = [line.strip() for line in res.stderr.splitlines() if line.strip()]
        err_msg = next((x for x in reversed(err_lines) if "ERROR:" in x), err_lines[-1] if err_lines else "Could not fetch video details.")
        raise RuntimeError(err_msg.replace("ERROR:", "").strip()[:300])

    data = json.loads(res.stdout.splitlines()[-1])
    is_playlist = data.get("_type") == "playlist" or bool(data.get("entries"))
    entries = data.get("entries") or []
    dur = data.get("duration")
    thumb = data.get("thumbnail") or (data["thumbnails"][-1].get("url", "") if data.get("thumbnails") else "")
    if not thumb and is_playlist and entries:
        first = entries[0] or {}
        thumb = first.get("thumbnail") or (first["thumbnails"][-1].get("url", "") if first.get("thumbnails") else "")

    return {
        "title": data.get("title") or "Untitled video",
        "uploader": data.get("uploader") or data.get("channel") or data.get("extractor_key") or "Video",
        "duration": format_seconds(int(dur)) if isinstance(dur, (int, float)) and dur > 0 else "",
        "duration_seconds": int(dur) if isinstance(dur, (int, float)) else 0,
        "thumbnail": thumb,
        "is_playlist": is_playlist,
        "playlist_count": len(entries) if is_playlist else 1,
        "webpage_url": data.get("webpage_url") or clean_url,
    }


def download(jid: str, url: str, folder: str, quality: str, fmt_choice: str, start_time: str = "", end_time: str = "", subtitles: bool = False, embed_thumbnail: bool = False, allow_playlist: bool = False):
    proc, started_at, out = None, time.time(), validate_folder(folder)
    try:
        if out is None:
            raise ValueError("Invalid or inaccessible save folder.")
        clean_url = extract_url(url)
        logging.info("Starting download [%s] %s", jid, clean_url)

        ffmpeg_bin = get_ffmpeg_path()
        has_ffmpeg = ffmpeg_bin is not None
        cmd = get_ytdlp_cmd() + ["--yes-playlist" if allow_playlist else "--no-playlist", "--newline", "--progress", "--windows-filenames"]
        if ffmpeg_bin:
            cmd.extend(["--ffmpeg-location", ffmpeg_bin])

        if fmt_choice in {"mp3", "m4a", "wav"}:
            if not has_ffmpeg and fmt_choice in {"mp3", "wav"}:
                raise RuntimeError(f"FFmpeg is required to convert audio to {fmt_choice.upper()}. Run setup-and-run.bat or choose M4A / MP4.")
            cmd.extend(["-x", "--audio-format", fmt_choice, "--audio-quality", "0"])
        elif has_ffmpeg:
            fmt = "bv*+ba/b" if quality == "best" else f"bv*[height<={quality}]+ba/b[height<={quality}]/b"
            cmd.extend(["--format", fmt, "--merge-output-format", fmt_choice])
        else:
            cmd.extend(["--format", "b" if quality == "best" else f"b[height<={quality}]/b"])

        if start_time or end_time:
            if not has_ffmpeg:
                raise RuntimeError("FFmpeg is required for cutting/trimming video clips.")
            s_sec = parse_timestamp(start_time) if start_time else 0
            e_sec = parse_timestamp(end_time) if end_time else None
            if s_sec is None or (end_time and e_sec is None) or (e_sec is not None and e_sec <= s_sec):
                raise ValueError("Invalid clip time range. Use MM:SS or HH:MM:SS.")
            cmd.extend(["--download-sections", f"*{s_sec}-{e_sec if e_sec is not None else 'inf'}", "--force-keyframes-at-cuts"])

        if subtitles:
            cmd.extend(["--write-subs", "--write-auto-subs", "--sub-langs", "en.*,bn.*"])
            if fmt_choice in {"mp4", "mkv", "webm"} and has_ffmpeg:
                cmd.append("--embed-subs")

        if embed_thumbnail and has_ffmpeg:
            cmd.append("--embed-thumbnail")

        cmd.extend(["--output", str(out / "%(title).180B [%(id)s].%(ext)s"), "--", clean_url])
        update(jid, state="Downloading", title="Starting download", detail="Connecting to video stream…", percent=0, speed="", eta="", stage="Preparing")

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", cwd=str(APP_DIR), bufsize=1)
        with lock:
            procs[jid] = proc

        recent, saved_file, stream_count = [], "", 0
        for raw in proc.stdout:
            with lock:
                if jobs.get(jid, {}).get("state") == "Cancelled":
                    terminate_process(proc)
                    break
            line = raw.strip()
            if not line:
                continue
            recent = (recent + [line])[-15:]

            for pat, inc in ((r"\[download\] Destination:\s+(.+)$", 1), (r'\[Merger\] Merging formats into "(.+?)"', 0), (r"\[ExtractAudio\] Destination:\s+(.+)$", 0), (r"\[download\]\s+(.+?)\s+has already been downloaded", 0)):
                m = re.search(pat, line)
                if m:
                    saved_file = m.group(1).strip().strip('"')
                    stream_count += inc

            prog = re.search(r"\[download\]\s+([\d.]+)%(?:\s+of\s+~?[\d.]+\w+)?(?:\s+at\s+([\d.]+\s*\w+/s))?(?:\s+ETA\s+([\d:]+))?", line)
            kw = {"detail": line[:600]}
            if prog:
                pct = float(prog.group(1))
                label = "Downloading audio" if fmt_choice in {"mp3", "m4a", "wav"} else ("Downloading video" if stream_count <= 1 else "Downloading audio track")
                kw.update(percent=pct, speed=(prog.group(2) or "").strip(), eta=(prog.group(3) or "").strip(), stage=label, title=f"{label} ({pct:.0f}%)")
            if "Merging formats" in line or "[Merger]" in line:
                kw.update(title="Merging video & audio (almost done)…", stage="Merging", speed="", eta="")
            elif "[ExtractAudio]" in line:
                kw.update(title="Converting audio format…", stage="Converting audio", speed="", eta="")
            elif "[EmbedThumbnail]" in line or "[EmbedSubtitle]" in line:
                kw.update(title="Embedding metadata…", stage="Finalizing")
            if saved_file:
                kw["file_path"] = saved_file
            update(jid, **kw)

        rc = proc.wait()
        with lock:
            procs.pop(jid, None)
            is_cancelled = jobs.get(jid, {}).get("state") == "Cancelled"

        if is_cancelled:
            cleanup_partial_files(out, started_at)
            update(jid, state="Cancelled", title="Download cancelled", detail="Download cancelled and temporary files cleaned up.", percent=0, speed="", eta="", stage="Cancelled")
        elif rc == 0:
            final_name = Path(saved_file).name if saved_file else ""
            if final_name and not jobs.get(jid, {}).get("video_title_locked"):
                clean_title = re.sub(r"\s*\[[A-Za-z0-9_-]{6,}\]\.[A-Za-z0-9]+$", "", final_name)
                if clean_title:
                    update(jid, video_title=clean_title)
            update(jid, state="Complete", title="Download complete!", detail=f"Saved: {final_name}" if final_name else f"Saved to: {out}", percent=100, speed="", eta="", stage="Complete", folder=str(out), file_path=saved_file or str(out))
        else:
            raw_err = next((x for x in reversed(recent) if "ERROR:" in x), recent[-1] if recent else "Download failed.").replace("ERROR:", "").strip()
            update(jid, state="Error", title="Download failed", detail=raw_err[:600], percent=0, speed="", eta="", stage="Error")
    except Exception as e:
        with lock:
            procs.pop(jid, None)
        update(jid, state="Error", title="Download failed", detail=str(e)[:600], percent=0, speed="", eta="", stage="Error")


def open_in_explorer(target_path: str) -> bool:
    if not target_path:
        return False
    p = Path(target_path).expanduser()
    if not p.exists():
        p = p.parent if p.parent.exists() else p
    if not p.exists():
        return False
    try:
        if os.name == "nt":
            subprocess.Popen(["explorer", f"/select,{p.resolve()}"]) if p.is_file() else os.startfile(str(p.resolve()))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p.resolve())] if p.is_file() else ["open", str(p.resolve())])
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
        if p.path in {"/", "/index.html", "/style.css", "/app.js", "/logo.svg"}:
            self.path = "/index.html" if p.path == "/" else p.path
            return super().do_GET()
        if p.path == "/api/config":
            with lock:
                recent_list = [{"id": k, **v} for k, v in list(jobs.items())[-10:]]
            return self.json(200, {"ok": True, "version": VERSION, "default_folder": str(DEFAULT_FOLDER), "ffmpeg": ffmpeg_available(), "jobs": recent_list})
        if p.path == "/api/ffmpeg":
            return self.json(200, {"ok": True, "available": ffmpeg_available()})
        if p.path == "/api/status":
            jid = parse_qs(p.query).get("id", [""])[0]
            with lock:
                data = dict(jobs[jid]) if jid in jobs else None
            return self.json(200, {"ok": True, **data}) if data else self.json(404, {"ok": False, "error": "Download job not found."})
        return self.json(404, {"ok": False, "error": "Not found."})

    def do_POST(self):
        origin = self.headers.get("Origin", "")
        if origin and not (origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:")):
            return self.json(403, {"ok": False, "error": "Request origin not allowed."})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n).decode("utf-8") if 0 < n <= 20000 else "{}")
        except Exception:
            return self.json(400, {"ok": False, "error": "Invalid request."})

        if self.path == "/api/info":
            url = extract_url(str(body.get("url", "")))
            if not valid_url(url):
                return self.json(400, {"ok": False, "error": "Enter a valid HTTPS link (YouTube, Facebook, Instagram, TikTok, X, etc.)."})
            try:
                return self.json(200, {"ok": True, "info": fetch_video_info(url)})
            except Exception as e:
                return self.json(400, {"ok": False, "error": str(e)})

        if self.path == "/api/download":
            url = extract_url(str(body.get("url", "")))
            validated_folder = validate_folder(body.get("folder", str(DEFAULT_FOLDER)))
            if not validated_folder:
                return self.json(400, {"ok": False, "error": "Invalid save folder. Please enter an accessible folder path."})
            if not valid_url(url):
                return self.json(400, {"ok": False, "error": "Enter a valid HTTPS link (YouTube, Facebook, Instagram, TikTok, X, etc.)."})
            fmt_choice = str(body.get("format", "mp4")).lower().strip()
            quality = str(body.get("quality", "best")).strip()
            if fmt_choice not in VALID_FORMATS or (fmt_choice in {"mp4", "mkv", "webm"} and quality not in VALID_QUALITIES):
                return self.json(400, {"ok": False, "error": "Choose a valid format and quality."})

            start_time, end_time = str(body.get("start_time", "")).strip(), str(body.get("end_time", "")).strip()
            if (start_time and parse_timestamp(start_time) is None) or (end_time and parse_timestamp(end_time) is None):
                return self.json(400, {"ok": False, "error": "Clip time must be in MM:SS or HH:MM:SS format (e.g. 01:20)."})
            if start_time and end_time and parse_timestamp(end_time) <= parse_timestamp(start_time):
                return self.json(400, {"ok": False, "error": "End time must be after start time."})

            subtitles = bool(body.get("subtitles", False))
            embed_thumbnail = bool(body.get("embed_thumbnail", False))
            allow_playlist = bool(body.get("allow_playlist", False))
            raw_hint = str(body.get("title_hint", "")).strip()

            jid, now = uuid.uuid4().hex, time.time()
            with lock:
                jobs[jid] = {
                    "state": "Queued", "title": "Download queued", "video_title": raw_hint or "Video download",
                    "video_title_locked": bool(raw_hint), "url": url, "format": fmt_choice.upper(),
                    "quality": "Audio" if fmt_choice in {"mp3", "m4a", "wav"} else ("Best" if quality == "best" else f"{quality}p"),
                    "detail": "Waiting to start…", "percent": 0, "speed": "", "eta": "", "stage": "Queued",
                    "folder": str(validated_folder), "file_path": str(validated_folder), "created_at": now, "updated_at": now,
                }
            threading.Thread(target=download, args=(jid, url, str(validated_folder), quality, fmt_choice, start_time, end_time, subtitles, embed_thumbnail, allow_playlist), daemon=True).start()
            return self.json(202, {"ok": True, "id": jid, "folder": str(validated_folder)})

        if self.path == "/api/cancel":
            jid = str(body.get("id", "")).strip()
            with lock:
                if jid in jobs:
                    jobs[jid]["state"] = "Cancelled"
                proc = procs.get(jid)
            if proc:
                terminate_process(proc)
            return self.json(200, {"ok": True})

        if self.path == "/api/open-folder":
            target = str(body.get("path", "")).strip()
            jid = str(body.get("id", "")).strip()
            if not target and jid:
                with lock:
                    target = jobs.get(jid, {}).get("file_path") or jobs.get(jid, {}).get("folder") or ""
            return self.json(200, {"ok": True}) if open_in_explorer(target or str(DEFAULT_FOLDER)) else self.json(400, {"ok": False, "error": "Could not open folder on this system."})

        if self.path == "/api/ffmpeg":
            return self.json(200, {"ok": True, "available": ffmpeg_available()})

        return self.json(404, {"ok": False, "error": "Not found."})


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--run-ytdlp":
        import yt_dlp
        sys.argv = ["yt-dlp"] + sys.argv[2:]
        yt_dlp.main()
        return

    if not HTML_FILE.exists():
        raise SystemExit(f"Missing HTML file: {HTML_FILE}")

    server, bound_port = None, None
    for port in range(8765, 8776):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            bound_port = port
            break
        except OSError:
            continue

    if not server or not bound_port:
        sys.exit("Error: Could not bind to any port between 8765 and 8775.")

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
