#!/usr/bin/env python3
"""Local-only backend for YT & FB Video Downloader."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path
import threading, subprocess, sys, json, uuid, re, webbrowser, tkinter as tk
from tkinter import filedialog
import logging

ROOT = Path(__file__).resolve().parent
HTML_FILE = ROOT / "index.html"
DEFAULT_FOLDER = Path(r"D:\Videos\Downloads")
logging.basicConfig(filename="app.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
ALLOWED = {"youtube.com", "youtu.be", "facebook.com", "fb.watch"}

lock = threading.Lock()
jobs = {}
procs = {}


def update(jid, **kwargs):
    with lock:
        if jid in jobs:
            jobs[jid].update(kwargs)


def valid_url(raw):
    p = urlparse(raw)
    if p.scheme != "https" or not p.hostname:
        return False
    host = p.hostname.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in ALLOWED)


def validate_folder(folder):
    p = Path(folder).expanduser()
    if not folder or not str(folder).strip():
        return None
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    if not p.is_dir():
        return None
    blocked = {Path.home().anchor, "C:\\"}
    if str(p.resolve()).lower() in {str(x).lower() for x in blocked}:
        return None
    return p


def ffmpeg_available():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False


def download(jid, url, folder, quality, fmt_choice):
    proc = None
    try:
        out = validate_folder(folder)
        if out is None:
            raise ValueError("Invalid or inaccessible save folder.")
        logging.info("Starting download %s", url)
        if fmt_choice in {"mp3", "m4a", "wav"}:
            cmd = [sys.executable, "-m", "yt_dlp", "--no-playlist", "--newline",
                   "--progress", "-x", "--audio-format", fmt_choice,
                   "--windows-filenames", "--output", str(out / "%(title).180B [%(id)s].%(ext)s"), url]
        else:
            fmt = "bv*+ba/b" if quality == "best" else f"bv*[height<={quality}]+ba/b[height<={quality}]/b"
            cmd = [sys.executable, "-m", "yt_dlp", "--no-playlist", "--newline",
                   "--progress", "--format", fmt, "--merge-output-format", fmt_choice,
                   "--windows-filenames", "--output", str(out / "%(title).180B [%(id)s].%(ext)s"), url]
        update(jid, state="Downloading", title="Starting download", detail="Launching download engine…", percent=0)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", cwd=str(ROOT), bufsize=1)
        with lock:
            procs[jid] = proc
        recent = []
        for raw in proc.stdout:
            # Check if cancelled
            with lock:
                job_state = jobs.get(jid, {}).get("state")
            if job_state == "Cancelled":
                try:
                    proc.terminate()
                except Exception:
                    pass
                break
            line = raw.strip()
            if not line:
                continue
            recent.append(line)
            recent = recent[-12:]
            match = re.search(r"\[download\]\s+([\d.]+)%", line)
            kwargs = {"detail": line[:600]}
            if match:
                kwargs["percent"] = float(match.group(1))
            if "Merging formats" in line or "ffmpeg" in line.lower():
                kwargs["title"] = "Processing video"
            update(jid, **kwargs)
        rc = proc.wait()
        with lock:
            procs.pop(jid, None)
        with lock:
            job_state = jobs.get(jid, {}).get("state")
        if job_state == "Cancelled":
            update(jid, state="Cancelled", title="Cancelled", detail="Download cancelled by user.", percent=0)
            return
        if rc == 0:
            update(jid, state="Complete", title="Download complete", detail=f"Saved to: {out}", percent=100)
        else:
            msg = next((x for x in reversed(recent) if "ERROR:" in x), recent[-1] if recent else "Download failed.")
            update(jid, state="Error", title="Download failed", detail=msg[:600], percent=0)
    except Exception as e:
        with lock:
            procs.pop(jid, None)
        update(jid, state="Error", title="Download failed", detail=str(e)[:600], percent=0)


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
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
        if origin and not (origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:")):
            return self.json(403, {"ok": False, "error": "Request origin not allowed."})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n > 20000:
                return self.json(413, {"ok": False, "error": "Request too large."})
            body = json.loads(self.rfile.read(n).decode() or "{}")
        except Exception:
            return self.json(400, {"ok": False, "error": "Invalid request."})

        if self.path == "/api/choose-folder":
            result = {}

            def pick_folder():
                try:
                    root = tk.Tk()
                    root.withdraw()
                    root.attributes("-topmost", True)
                    initial = str(DEFAULT_FOLDER if DEFAULT_FOLDER.exists() else Path.home())
                    folder = filedialog.askdirectory(title="Choose video download folder", initialdir=initial)
                    root.destroy()
                    result["folder"] = folder or ""
                except Exception as e:
                    result["error"] = str(e)

            t = threading.Thread(target=pick_folder, daemon=True)
            t.start()
            t.join(timeout=60)
            if "error" in result:
                return self.json(500, {"ok": False, "error": f"Folder picker failed: {result['error']}"})
            return self.json(200, {"ok": True, "folder": result.get("folder", "")})

        if self.path == "/api/download":
            url = str(body.get("url", "")).strip()
            folder = str(body.get("folder", str(DEFAULT_FOLDER))).strip()
            if not validate_folder(folder):
                return self.json(400, {"ok": False, "error": "Invalid save folder."})
            quality = str(body.get("quality", "best"))
            if not valid_url(url):
                return self.json(400, {"ok": False, "error": "Enter a valid HTTPS YouTube or Facebook URL."})
            fmt_choice = str(body.get("format", "mp4")).lower()
            if fmt_choice not in {"mp4", "mkv", "webm", "mp3", "m4a", "wav"}:
                return self.json(400, {"ok": False, "error": "Choose a valid format."})
            if fmt_choice in {"mp4", "mkv", "webm"} and quality not in {"best", "1080", "720", "480"}:
                return self.json(400, {"ok": False, "error": "Choose a valid quality."})
            if not folder:
                return self.json(400, {"ok": False, "error": "Choose a save folder."})
            jid = uuid.uuid4().hex
            with lock:
                jobs[jid] = {"state": "Queued", "title": "Download queued", "detail": "Waiting to start…", "percent": 0}
            threading.Thread(target=download, args=(jid, url, folder, quality, fmt_choice), daemon=True).start()
            return self.json(202, {"ok": True, "id": jid})

        if self.path == "/api/cancel":
            jid = str(body.get("id", "")).strip()
            with lock:
                if jid in jobs:
                    jobs[jid]["state"] = "Cancelled"
                proc = procs.get(jid)
            if proc:
                try:
                    proc.terminate()
                except Exception:
                    pass
            return self.json(200, {"ok": True})

        if self.path == "/api/ffmpeg":
            return self.json(200, {"ok": True, "available": ffmpeg_available()})
        return self.json(404, {"ok": False, "error": "Not found."})


def main():
    if not HTML_FILE.exists():
        raise SystemExit(f"Missing HTML file: {HTML_FILE}")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    except OSError as e:
        print(f"Error: Could not bind to port 8765. Port may already be in use. {e}")
        sys.exit(1)
    print("ClipHaven — Catch, keep, and enjoy your clips. running at http://127.0.0.1:8765/")
    print("Keep this window open while downloading. Ctrl+C stops the app.")
    threading.Timer(0.7, lambda: webbrowser.open("http://127.0.0.1:8765/")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
