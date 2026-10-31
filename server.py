#!/usr/bin/env python3
"""Local-only backend for ClipHaven Video & Audio Downloader (v3.2.0).
Developed by Md Asadullah Al Munib (https://github.com/AsadullahAlMunib/ClipHaven/)."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
import urllib.request
from pathlib import Path
import threading
import subprocess
import signal
import shutil
import sys
import os
import json
import uuid
import re
import time
import webbrowser
import logging

VERSION = "3.2.0"
AUTHOR = "Md Asadullah Al Munib"
REPO_URL = "https://github.com/AsadullahAlMunib/ClipHaven/"
IS_FROZEN = getattr(sys, "frozen", False)
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) if IS_FROZEN else Path(__file__).resolve().parent
APP_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent
HTML_FILE = BUNDLE_DIR / "index.html"
DEFAULT_FOLDER = (Path.home() / "Downloads" / "ClipHaven") if (Path.home() / "Downloads").exists() else (APP_DIR / "downloads")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ALLOWED = {
    "youtube.com", "youtu.be", "youtube-nocookie.com", "facebook.com", "fb.watch", "fb.com", "fb.gg",
    "instagram.com", "instagr.am", "threads.net", "threads.com", "linkedin.com", "lnkd.in",
    "tiktok.com", "twitter.com", "x.com", "t.co", "reddit.com", "redd.it", "vimeo.com",
    "dailymotion.com", "dai.ly", "twitch.tv", "pinterest.com", "pin.it", "soundcloud.com", "snd.sc",
}
VALID_FORMATS = {"mp4", "mkv", "webm", "mp3", "m4a", "wav"}
VALID_QUALITIES = {"best", "2160", "1440", "1080", "720", "480", "360"}
SUB_OR_THUMB_EXTS = {".vtt", ".srt", ".ass", ".ssa", ".ttml", ".srv1", ".srv2", ".srv3", ".json3", ".webp", ".jpg", ".jpeg", ".png"}
SUB_TEXT_EXTS = {".vtt", ".srt"}
SUB_SHIFT_MARKER = "\u2060"
_SUB_TS_LINE_RE = re.compile(r"((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})(.*)")
_SUB_INLINE_TS_RE = re.compile(r"<((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})>")
MAX_JOBS = 40

lock = threading.Lock()
_ffmpeg_lock = threading.Lock()
jobs = {}
procs = {}
_FFMPEG_CACHED_PATH: str | None = None


def get_ytdlp_cmd() -> list[str]:
    return [sys.executable, "--run-ytdlp"] if IS_FROZEN else [sys.executable, "-m", "yt_dlp"]


def get_ffmpeg_path() -> str | None:
    """Locate ffmpeg binary path thread-safely and cache only when found."""
    global _FFMPEG_CACHED_PATH
    with _ffmpeg_lock:
        if _FFMPEG_CACHED_PATH and Path(_FFMPEG_CACHED_PATH).is_file():
            return _FFMPEG_CACHED_PATH

        exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        for base in (APP_DIR, BUNDLE_DIR):
            candidate = base / exe_name
            if candidate.is_file() and candidate.stat().st_size > 0:
                if os.name != "nt" and not os.access(candidate, os.X_OK):
                    try:
                        candidate.chmod(0o755)
                    except Exception:
                        pass
                _FFMPEG_CACHED_PATH = str(candidate)
                return _FFMPEG_CACHED_PATH

        which_ff = shutil.which("ffmpeg")
        if which_ff:
            _FFMPEG_CACHED_PATH = which_ff
            return _FFMPEG_CACHED_PATH

        try:
            import imageio_ffmpeg
            pkg_ff = imageio_ffmpeg.get_ffmpeg_exe()
            if pkg_ff and Path(pkg_ff).is_file():
                local_target = APP_DIR / exe_name
                if not local_target.exists() or local_target.stat().st_size == 0:
                    tmp_target = APP_DIR / f"{exe_name}.{os.getpid()}.tmp"
                    try:
                        shutil.copyfile(pkg_ff, tmp_target)
                        if os.name != "nt":
                            tmp_target.chmod(0o755)
                        os.replace(tmp_target, local_target)
                        _FFMPEG_CACHED_PATH = str(local_target)
                        return _FFMPEG_CACHED_PATH
                    except Exception:
                        try:
                            tmp_target.unlink(missing_ok=True)
                        except Exception:
                            pass
                        _FFMPEG_CACHED_PATH = str(pkg_ff)
                        return _FFMPEG_CACHED_PATH
                _FFMPEG_CACHED_PATH = str(local_target)
                return _FFMPEG_CACHED_PATH
        except Exception:
            pass

        if os.name == "nt":
            winget_pkgs = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
            if winget_pkgs.exists():
                for exe in winget_pkgs.rglob("ffmpeg.exe"):
                    _FFMPEG_CACHED_PATH = str(exe)
                    return _FFMPEG_CACHED_PATH
        return None


def ffmpeg_available() -> bool:
    return get_ffmpeg_path() is not None


def _is_allowed_host(host: str) -> bool:
    h = (host or "").lower().rstrip(".")
    return any(h == d or h.endswith("." + d) for d in ALLOWED)


def extract_url(raw: str) -> str:
    if not raw:
        return ""
    s = str(raw).strip()
    m = re.search(r"https?://[^\s<>\"']+", s)
    if m:
        return m.group(0).rstrip(".,;)!]>")
    m_bare = re.search(r"(?:www\.)?(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}/[^\s<>\"']*", s)
    if m_bare:
        candidate = m_bare.group(0).rstrip(".,;)!]>")
        host_part = candidate.split("/", 1)[0].lower()
        if _is_allowed_host(host_part):
            return "https://" + candidate
    return s


def valid_url(raw: str) -> bool:
    url = extract_url(raw)
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme != "https" or not p.hostname:
        return False
    return _is_allowed_host(p.hostname)


def validate_folder(folder) -> Path | None:
    if not folder or not str(folder).strip():
        return None
    raw = str(folder).strip()
    if re.match(r"^[a-zA-Z]:[\\/]*$", raw) or raw in {"/", "\\"}:
        return None
    try:
        raw_low = raw.lower()
        if raw_low.startswith("downloads/") or raw_low == "downloads":
            sub = raw[10:].lstrip("/\\") if raw_low.startswith("downloads/") else ""
            p = (Path.home() / "Downloads" / sub) if (Path.home() / "Downloads").exists() else (APP_DIR / "downloads" / sub)
        elif raw_low.startswith("internal storage/") or raw_low == "internal storage":
            sub = raw[17:].lstrip("/\\") if raw_low.startswith("internal storage/") else ""
            p = (Path.home() / "Downloads" / sub) if (Path.home() / "Downloads").exists() else (APP_DIR / "downloads" / sub)
        else:
            p = Path(raw).expanduser()
            if not p.is_absolute():
                p = (APP_DIR / p).resolve()
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
    sec = max(0, int(sec))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def parse_sub_timestamp_ms(ts: str) -> int:
    clean = str(ts).strip().replace(",", ".")
    parts = clean.split(":")
    if len(parts) == 3:
        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
    elif len(parts) == 2:
        h, m, s = 0, int(parts[0]), float(parts[1])
    else:
        return 0
    return int(round((h * 3600 + m * 60 + s) * 1000))


def format_sub_timestamp_ms(ms: int, sep: str = ".") -> str:
    clean = max(0, int(ms))
    h, rem = divmod(clean, 3600000)
    m, rem = divmod(rem, 60000)
    s, millis = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{millis:03d}"


def trim_and_shift_subtitle_text(content: str, start_sec: float, end_sec: float | None, is_vtt: bool = True) -> str:
    """Trim subtitle cues to [start_sec, end_sec] and shift timestamps back by start_sec so clips start at 00:00:00."""
    if not content or SUB_SHIFT_MARKER in content:
        return content
    start_ms = max(0, int(round((start_sec or 0) * 1000)))
    end_ms = int(round(end_sec * 1000)) if end_sec is not None else None
    if start_ms == 0 and end_ms is None:
        return content

    sep = "." if is_vtt else ","
    blocks = re.split(r"\r?\n\r?\n+", content.lstrip("\ufeff").strip())
    header_blocks: list[str] = []
    cue_blocks: list[tuple[int, int, str, list[str]]] = []

    def _shift_inline(match: re.Match) -> str:
        raw_ms = parse_sub_timestamp_ms(match.group(1))
        shifted = max(0, raw_ms - start_ms)
        if end_ms is not None:
            shifted = min(shifted, max(0, end_ms - start_ms))
        return f"<{format_sub_timestamp_ms(shifted, sep)}>"

    for block in blocks:
        lines = [ln.rstrip("\r") for ln in block.split("\n")]
        ts_idx = None
        for idx, ln in enumerate(lines):
            if "-->" in ln and _SUB_TS_LINE_RE.search(ln):
                ts_idx = idx
                break
        if ts_idx is None:
            if is_vtt and not cue_blocks and lines and (
                lines[0].startswith("WEBVTT")
                or lines[0].startswith("Kind:")
                or lines[0].startswith("Language:")
                or lines[0].startswith("NOTE")
                or lines[0].startswith("STYLE")
            ):
                header_blocks.append("\n".join(lines))
            continue

        m = _SUB_TS_LINE_RE.search(lines[ts_idx])
        if not m:
            continue
        c_start = parse_sub_timestamp_ms(m.group(1))
        c_end = parse_sub_timestamp_ms(m.group(2))
        settings = m.group(3) or ""
        if c_end <= start_ms:
            continue
        if end_ms is not None and c_start >= end_ms:
            continue

        new_start = max(0, c_start - start_ms)
        new_end = (min(c_end, end_ms) if end_ms is not None else c_end) - start_ms
        if new_end <= new_start:
            continue

        payload = [_SUB_INLINE_TS_RE.sub(_shift_inline, ln) for ln in lines[ts_idx + 1:] if ln.strip()]
        if not payload:
            continue
        cue_blocks.append((new_start, new_end, settings, payload))

    if not cue_blocks:
        cue_blocks.append((0, 100, "", ["\u200b"]))

    first_s, first_e, first_set, first_pay = cue_blocks[0]
    first_pay = list(first_pay)
    first_pay[-1] = first_pay[-1] + SUB_SHIFT_MARKER
    cue_blocks[0] = (first_s, first_e, first_set, first_pay)

    out_blocks: list[str] = []
    if is_vtt:
        out_blocks.extend(header_blocks if header_blocks else ["WEBVTT"])
    for idx, (ns, ne, settings, payload) in enumerate(cue_blocks, 1):
        ts_line = f"{format_sub_timestamp_ms(ns, sep)} --> {format_sub_timestamp_ms(ne, sep)}{settings}"
        if is_vtt:
            out_blocks.append(ts_line + "\n" + "\n".join(payload))
        else:
            out_blocks.append(f"{idx}\n{ts_line}\n" + "\n".join(payload))
    return "\n\n".join(out_blocks) + "\n"


def trim_and_shift_subtitle_file(sub_path: Path, start_sec: float, end_sec: float | None) -> bool:
    """Trim and time-shift a .vtt or .srt file atomically in-place if not already shifted."""
    try:
        if not sub_path.is_file() or sub_path.stat().st_size == 0:
            return False
        ext = sub_path.suffix.lower()
        if ext not in SUB_TEXT_EXTS:
            return False
        raw = sub_path.read_text(encoding="utf-8", errors="replace")
        if SUB_SHIFT_MARKER in raw:
            return False
        shifted = trim_and_shift_subtitle_text(raw, start_sec, end_sec, is_vtt=(ext == ".vtt"))
        if shifted == raw:
            return False
        tmp_path = sub_path.with_name(f"{sub_path.name}.{os.getpid()}.cliphaven.tmp")
        tmp_path.write_text(shifted, encoding="utf-8")
        os.replace(tmp_path, sub_path)
        return True
    except Exception:
        return False


def _has_active_video_file_in_dir(folder: Path, started_at: float, clip_suffix: str) -> bool:
    """Check if yt-dlp/ffmpeg has started creating the clipped video stream file on disk (which happens only after before_dl finishes)."""
    try:
        for f in folder.iterdir():
            if not f.is_file():
                continue
            name_low = f.name.lower()
            if name_low.endswith(".cliphaven.tmp") or name_low.endswith(".ytdl"):
                continue
            if clip_suffix and clip_suffix not in f.name:
                continue
            st = f.stat()
            if max(st.st_mtime, st.st_ctime) < started_at - 5:
                continue
            # Strip .part or .temp to inspect the media extension
            clean_name = re.sub(r"\.(?:part|temp)(?:-\w+)?$", "", name_low)
            ext = Path(clean_name).suffix.lower()
            if ext in {".mp4", ".mkv", ".webm", ".m4a"}:
                return True
    except Exception:
        pass
    return False


def sync_clip_subtitles_in_dir(
    folder: Path,
    started_at: float,
    start_sec: float,
    end_sec: float | None,
    clip_suffix: str = "",
    expect_srt: bool = False,
) -> int:
    """Trim and time-shift all completed subtitle files for a clip job before FFmpeg embeds them."""
    count = 0
    try:
        entries = list(folder.iterdir())
        if expect_srt:
            # Wait until SubtitlesConvertor (before_dl) has finished converting and deleting all .vtt files for this job
            for f in entries:
                if not f.is_file() or f.suffix.lower() != ".vtt":
                    continue
                if clip_suffix and clip_suffix not in f.name:
                    continue
                st = f.stat()
                if max(st.st_mtime, st.st_ctime) >= started_at - 5:
                    return 0

        for f in entries:
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            if ext not in SUB_TEXT_EXTS or f.name.endswith(".cliphaven.tmp"):
                continue
            if expect_srt and ext != ".srt":
                continue
            st = f.stat()
            if max(st.st_mtime, st.st_ctime) < started_at - 5:
                continue
            if clip_suffix and clip_suffix not in f.name:
                continue
            if trim_and_shift_subtitle_file(f, start_sec, end_sec):
                count += 1
    except Exception:
        pass
    return count


def terminate_process(proc: subprocess.Popen):
    if not proc:
        return
    try:
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=4,
                )
            except Exception:
                try:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception:
                    pass
                proc.terminate()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def cleanup_partial_files(folder: Path, started_at: float, target_file: str = "", is_clip_job: bool = False):
    time.sleep(0.25)
    try:
        if target_file:
            tp = Path(target_file)
            stem = tp.stem
            # Clean up partial/temp files matching this specific download's filename stem
            for f in folder.iterdir():
                if not f.is_file():
                    continue
                if f.name.startswith(stem) and (
                    is_clip_job
                    or ".part" in f.name
                    or ".temp" in f.name
                    or f.suffix in {".ytdl", ".vtt", ".srt", ".webp"}
                    or re.search(r"\.f\d+\.", f.name)
                ):
                    try:
                        f.unlink(missing_ok=True)
                    except Exception:
                        pass
            return

        # Fallback when cancelled before Destination filename was printed:
        # Only sweep recent partial files if no other job is actively downloading in the same folder.
        with lock:
            other_active = any(
                v.get("state") in {"Queued", "Downloading"} and v.get("folder") == str(folder)
                for v in jobs.values()
            )
        if other_active:
            return

        for pattern in ("*.part*", "*.ytdl", "*.temp*", "*.f[0-9]*.*"):
            for f in folder.glob(pattern):
                try:
                    st = f.stat()
                    if max(st.st_mtime, st.st_ctime) >= started_at - 5:
                        f.unlink(missing_ok=True)
                except Exception:
                    pass
    except Exception:
        pass


def update(jid: str, **kwargs):
    with lock:
        if jid in jobs:
            if jobs[jid].get("state") == "Cancelled" and kwargs.get("state") != "Cancelled":
                return
            jobs[jid].update(kwargs, updated_at=time.time())


def prune_jobs():
    with lock:
        if len(jobs) <= MAX_JOBS:
            return
        done = [k for k, v in jobs.items() if v.get("state") in {"Complete", "Error", "Cancelled"}]
        for k in done[: max(0, len(jobs) - MAX_JOBS)]:
            jobs.pop(k, None)


_update_cache: dict = {"checked_at": 0.0, "data": None}
UPDATE_CACHE_TTL = 4 * 3600  # 4 hours to respect GitHub API rate limits
GITHUB_LATEST_RELEASE_API = "https://api.github.com/repos/AsadullahAlMunib/ClipHaven/releases/latest"


def parse_semver(ver: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", str(ver or ""))
    return tuple(int(x) for x in nums[:4]) if nums else (0, 0, 0)


def is_newer_version(latest: str, current: str = VERSION) -> bool:
    return parse_semver(latest) > parse_semver(current)


def check_github_update(force: bool = False) -> dict:
    now = time.time()
    with lock:
        cached = _update_cache.get("data")
        if not force and cached and (now - _update_cache.get("checked_at", 0.0) < UPDATE_CACHE_TTL):
            return dict(cached)

    try:
        req = urllib.request.Request(
            GITHUB_LATEST_RELEASE_API,
            headers={
                "User-Agent": f"ClipHaven/{VERSION}",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                raise RuntimeError(f"GitHub API HTTP {resp.status}")
            rel = json.loads(resp.read().decode("utf-8", errors="replace"))

        tag = str(rel.get("tag_name") or "").strip().lstrip("vV")
        if not tag:
            raise RuntimeError("Missing release tag")
        notes = str(rel.get("body") or "Bug fixes and performance improvements.").strip()
        html_url = str(rel.get("html_url") or f"{REPO_URL.rstrip('/')}/releases/latest").strip()
        result = {
            "ok": True,
            "update_available": is_newer_version(tag, VERSION),
            "current_version": VERSION,
            "latest_version": tag,
            "release_title": str(rel.get("name") or f"ClipHaven v{tag}").strip(),
            "release_notes": notes[:4000],
            "release_url": html_url,
            "is_android": False,
        }
        with lock:
            _update_cache["checked_at"] = now
            _update_cache["data"] = dict(result)
        return result
    except Exception:
        with lock:
            if _update_cache.get("data"):
                return dict(_update_cache["data"])
        return {
            "ok": True,
            "update_available": False,
            "current_version": VERSION,
            "latest_version": VERSION,
            "release_title": "",
            "release_notes": "",
            "release_url": f"{REPO_URL.rstrip('/')}/releases/latest",
            "is_android": False,
        }


_info_cache: dict[str, dict] = {}
_YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")


def _extract_yt_id(url: str) -> str:
    m = _YT_ID_RE.search(url or "")
    return m.group(1) if m else ""


def _fetch_fast_oembed_info(clean_url: str, parsed, has_video_and_list: bool) -> dict | None:
    """Instant (~200ms) lightweight preview via official oEmbed APIs before falling back to yt-dlp."""
    host = (parsed.hostname or "").lower().rstrip(".")
    oembed_url = ""
    yt_id = ""
    is_playlist = has_video_and_list or "/playlist" in (parsed.path or "")

    if any(host == d or host.endswith("." + d) for d in ("youtube.com", "youtu.be", "youtube-nocookie.com")):
        yt_id = _extract_yt_id(clean_url)
        target = f"https://www.youtube.com/watch?v={yt_id}" if yt_id else clean_url
        oembed_url = f"https://www.youtube.com/oembed?url={quote(target, safe='')}&format=json"
    elif host == "tiktok.com" or host.endswith(".tiktok.com"):
        oembed_url = f"https://www.tiktok.com/oembed?url={quote(clean_url, safe='')}"
    elif host == "vimeo.com" or host.endswith(".vimeo.com"):
        oembed_url = f"https://vimeo.com/api/oembed.json?url={quote(clean_url, safe='')}"
    elif any(host == d or host.endswith("." + d) for d in ("dailymotion.com", "dai.ly")):
        oembed_url = f"https://www.dailymotion.com/services/oembed?url={quote(clean_url, safe='')}&format=json"
    elif any(host == d or host.endswith("." + d) for d in ("soundcloud.com", "snd.sc")):
        oembed_url = f"https://soundcloud.com/oembed?format=json&url={quote(clean_url, safe='')}"
    elif any(host == d or host.endswith("." + d) for d in ("reddit.com", "redd.it")):
        oembed_url = f"https://www.reddit.com/oembed?url={quote(clean_url, safe='')}"

    if not oembed_url:
        return None

    try:
        req = urllib.request.Request(
            oembed_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        title = (data.get("title") or "").strip()
        if not title:
            return None
        thumb = (data.get("thumbnail_url") or "").strip()
        if not thumb and yt_id:
            thumb = f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg"
        dur = data.get("duration")
        dur_sec = int(dur) if isinstance(dur, (int, float)) and dur > 0 else 0
        return {
            "title": title,
            "uploader": (data.get("author_name") or data.get("provider_name") or "Video").strip(),
            "duration": format_seconds(dur_sec) if dur_sec > 0 else "",
            "duration_seconds": dur_sec,
            "thumbnail": thumb,
            "is_playlist": is_playlist,
            "playlist_count": 2 if is_playlist else 1,
            "webpage_url": clean_url,
        }
    except Exception:
        return None


def fetch_video_info(url: str) -> dict:
    clean_url = extract_url(url)
    if not valid_url(clean_url):
        raise ValueError("Enter a valid HTTPS video URL (YouTube, Facebook, Instagram, LinkedIn, TikTok, X, etc.).")

    with lock:
        if clean_url in _info_cache:
            return dict(_info_cache[clean_url])

    parsed = urlparse(clean_url)
    qs = parse_qs(parsed.query)
    has_list_param = bool(qs.get("list")) or "/playlist" in (parsed.path or "")
    has_video_and_list = bool(qs.get("list")) and bool(qs.get("v") or parsed.hostname in {"youtu.be"})

    # 1. Fast-path: try lightweight oEmbed API (~0.2s) for single videos (when not a playlist URL)
    if not has_list_param:
        fast_info = _fetch_fast_oembed_info(clean_url, parsed, False)
        if fast_info:
            fast_info["entries"] = []
            with lock:
                if len(_info_cache) >= 64:
                    _info_cache.pop(next(iter(_info_cache)), None)
                _info_cache[clean_url] = dict(fast_info)
            return fast_info

    # 2. Extract flat playlist entries (up to 100 items) or single video metadata via in-process yt_dlp or subprocess
    data = None
    try:
        import yt_dlp  # type: ignore
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False if has_list_param else True,
            "extract_flat": "in_playlist",
            "playlistend": 100,
            "socket_timeout": 10,
            "source_address": "0.0.0.0",
            "extractor_args": {"youtube": {"player_client": ["android", "web", "default"], "player_skip": ["configs"]}},
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            data = ydl.extract_info(clean_url, download=False)
    except Exception:
        data = None

    if not isinstance(data, dict):
        playlist_flags = ["--yes-playlist", "--flat-playlist", "--playlist-end", "100"] if has_list_param else ["--no-playlist"]
        cmd = get_ytdlp_cmd() + [
            "--dump-single-json",
            "--force-ipv4",
            "--socket-timeout",
            "10",
            *playlist_flags,
            "--extractor-args",
            "youtube:player_client=android,web,default;player_skip=configs",
            "--no-warnings",
            "--",
            clean_url,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", timeout=18, cwd=str(APP_DIR))
        if res.returncode != 0 or not res.stdout.strip():
            # If playlist extraction failed on a watch?v=...&list=... link (e.g. private Mix), fall back to fast single-video oEmbed
            if has_video_and_list:
                fast_info = _fetch_fast_oembed_info(clean_url, parsed, True)
                if fast_info:
                    fast_info["entries"] = []
                    return fast_info
            err_lines = [line.strip() for line in res.stderr.splitlines() if line.strip()]
            err_msg = next((x for x in reversed(err_lines) if "ERROR:" in x), err_lines[-1] if err_lines else "Could not fetch video details.")
            raise RuntimeError(err_msg.replace("ERROR:", "").strip()[:300])

        raw_out = res.stdout.strip()
        try:
            data = json.loads(raw_out)
        except json.JSONDecodeError:
            json_line = next((ln.strip() for ln in reversed(raw_out.splitlines()) if ln.strip().startswith("{")), raw_out.splitlines()[-1])
            data = json.loads(json_line)

    raw_entries = [e for e in (data.get("entries") or []) if isinstance(e, dict)]
    playlist_entries = []
    for idx, entry in enumerate(raw_entries, 1):
        edur = entry.get("duration")
        playlist_entries.append({
            "index": idx,
            "id": str(entry.get("id") or ""),
            "title": str(entry.get("title") or f"Video {idx}"),
            "duration": format_seconds(int(edur)) if isinstance(edur, (int, float)) and edur > 0 else "",
        })

    is_playlist = has_list_param or data.get("_type") == "playlist" or bool(playlist_entries)
    dur = data.get("duration")
    thumb = data.get("thumbnail") or (data["thumbnails"][-1].get("url", "") if data.get("thumbnails") else "")
    if not thumb and is_playlist and raw_entries:
        first = raw_entries[0]
        thumb = first.get("thumbnail") or (first["thumbnails"][-1].get("url", "") if first.get("thumbnails") else "")
    if not thumb:
        yt_id = _extract_yt_id(clean_url)
        if yt_id:
            thumb = f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg"

    result = {
        "title": data.get("title") or "Untitled video",
        "uploader": data.get("uploader") or data.get("channel") or data.get("creator") or data.get("extractor_key") or "Video",
        "duration": format_seconds(int(dur)) if isinstance(dur, (int, float)) and dur > 0 else "",
        "duration_seconds": int(dur) if isinstance(dur, (int, float)) else 0,
        "thumbnail": thumb,
        "is_playlist": is_playlist,
        "playlist_count": len(playlist_entries) if playlist_entries else (data.get("playlist_count") or (2 if is_playlist else 1)),
        "entries": playlist_entries,
        "webpage_url": data.get("webpage_url") or clean_url,
    }
    with lock:
        if len(_info_cache) >= 64:
            _info_cache.pop(next(iter(_info_cache)), None)
        _info_cache[clean_url] = dict(result)
    return result


_PLAYLIST_ITEMS_RE = re.compile(r"^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$")


def validate_playlist_items(raw: str) -> str | None:
    if not raw or not str(raw).strip():
        return ""
    cleaned = re.sub(r"\s+", "", str(raw))
    return cleaned if _PLAYLIST_ITEMS_RE.match(cleaned) else None


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
    duration_hint: int = 0,
    playlist_items: str = "",
):
    proc, started_at, out = None, time.time(), validate_folder(folder)
    saved_file = ""
    is_clip_job = False
    sub_watcher_stop = threading.Event()
    sub_sync_lock = threading.Lock()
    try:
        if out is None:
            raise ValueError("Invalid or inaccessible save folder.")
        clean_url = extract_url(url)
        logging.info("Starting download [%s] %s", jid, clean_url)

        ffmpeg_bin = get_ffmpeg_path()
        has_ffmpeg = ffmpeg_bin is not None
        cmd = get_ytdlp_cmd() + [
            "--yes-playlist" if allow_playlist else "--no-playlist",
            "--force-ipv4",
            "--concurrent-fragments",
            "4",
            "--retries",
            "10",
            "--fragment-retries",
            "10",
            "--socket-timeout",
            "20",
            "--newline",
            "--progress",
            "--no-mtime",
            "--windows-filenames",
            "--extractor-args",
            "youtube:player_client=android,web,default;skip=translated_subs",
        ]
        if allow_playlist:
            cmd.append("--ignore-errors")
            if playlist_items:
                cmd.extend(["--playlist-items", playlist_items])
        if ffmpeg_bin:
            cmd.extend(["--ffmpeg-location", ffmpeg_bin])

        if fmt_choice in {"mp3", "m4a", "wav"}:
            if not has_ffmpeg and fmt_choice in {"mp3", "wav"}:
                raise RuntimeError(f"FFmpeg is required to convert audio to {fmt_choice.upper()}. Run setup-and-run.bat or choose M4A / MP4.")
            cmd.extend(["-x", "--audio-format", fmt_choice, "--audio-quality", "0"])
        elif has_ffmpeg:
            if fmt_choice == "mp4":
                fmt = (
                    "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b[ext=mp4]/b"
                    if quality == "best"
                    else f"bv*[ext=mp4][height<={quality}]+ba[ext=m4a]/bv*[height<={quality}]+ba/b[height<={quality}]/b"
                )
            else:
                fmt = "bv*+ba/b" if quality == "best" else f"bv*[height<={quality}]+ba/b[height<={quality}]/b"
            cmd.extend(["--format", fmt, "--merge-output-format", fmt_choice])
        else:
            cmd.extend(["--format", "b" if quality == "best" else f"b[height<={quality}]/b"])

        clip_suffix = ""
        clip_duration = 0
        s_sec = parse_timestamp(start_time) if start_time else 0
        e_sec = parse_timestamp(end_time) if end_time else None
        if (start_time and s_sec is None) or (end_time and e_sec is None) or (e_sec is not None and s_sec is not None and e_sec <= s_sec):
            raise ValueError("Invalid clip time range. Use MM:SS or HH:MM:SS.")

        is_clip_job = bool((s_sec and s_sec > 0) or e_sec is not None)
        if is_clip_job:
            if not has_ffmpeg:
                raise RuntimeError("FFmpeg is required for cutting/trimming video clips.")
            if e_sec is not None:
                clip_duration = max(1, e_sec - (s_sec or 0))
            elif duration_hint and duration_hint > (s_sec or 0):
                clip_duration = max(1, int(duration_hint) - (s_sec or 0))
            ff_dl_args = "ffmpeg:-preset ultrafast -stats -v warning" if fmt_choice in {"mp4", "mkv", "webm"} else "ffmpeg:-stats -v warning"
            cmd.extend([
                "--download-sections",
                f"*{s_sec or 0}-{e_sec if e_sec is not None else 'inf'}",
                "--force-keyframes-at-cuts",
                "--no-embed-chapters",
                "--downloader-args",
                ff_dl_args,
            ])
            clip_suffix = f" [clip {(start_time or '0').replace(':', '-')}_to_{(end_time or 'end').replace(':', '-')}]"

        expect_srt_subs = bool(subtitles and has_ffmpeg and fmt_choice in {"mp4", "mkv"})
        if subtitles and fmt_choice in {"mp4", "mkv", "webm"}:
            # Download the video's exact original spoken language caption (.*-orig) plus manual BN/EN captions while skipping
            # machine-translated tracks (skip=translated_subs), matching YouTube's native CC button behavior for any language.
            cmd.extend([
                "--write-subs",
                "--write-auto-subs",
                "--sub-langs",
                ".*-orig,bn,en",
                "--compat-options",
                "no-keep-subs",
                "--ignore-errors",
            ])
            if has_ffmpeg:
                if fmt_choice in {"mp4", "mkv"}:
                    cmd.extend(["--convert-subs", "srt"])
                if is_clip_job and clip_duration > 0:
                    cmd.extend(["--postprocessor-args", f"EmbedSubtitle+ffmpeg_o:-t {clip_duration}"])
                cmd.append("--embed-subs")

        if embed_thumbnail and has_ffmpeg and fmt_choice in {"mp4", "mkv", "mp3", "m4a"}:
            # Convert WebP thumbnails to JPG first so MP4/M4A/MP3 containers never reject the cover art format.
            cmd.extend(["--convert-thumbnails", "jpg", "--embed-thumbnail"])

        cmd.extend(["--output", str(out / f"%(title).160B [%(id)s]{clip_suffix}.%(ext)s"), "--", clean_url])

        with lock:
            if jobs.get(jid, {}).get("state") == "Cancelled":
                cleanup_partial_files(out, started_at, saved_file, is_clip_job)
                return

        update(
            jid,
            state="Downloading",
            title="Preparing clip cutter…" if is_clip_job else "Starting download",
            detail="Connecting to media stream…",
            percent=0,
            indeterminate=is_clip_job,
            speed="",
            eta="",
            stage="Cutting clip" if is_clip_job else "Preparing",
        )

        child_env = os.environ.copy()
        child_env["PYTHONUNBUFFERED"] = "1"
        popen_kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", cwd=str(APP_DIR), bufsize=1, env=child_env)
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen(cmd, **popen_kwargs)
        with lock:
            if jobs.get(jid, {}).get("state") == "Cancelled":
                terminate_process(proc)
            else:
                procs[jid] = proc

        recent, stream_count = [], 0
        pl_idx, pl_total = 0, 0
        clip_started_ts = time.time()
        media_phase_started = False

        def _try_sync_subs():
            if not (is_clip_job and subtitles):
                return
            if not media_phase_started and not _has_active_video_file_in_dir(out, started_at, clip_suffix):
                return
            with sub_sync_lock:
                sync_clip_subtitles_in_dir(
                    out,
                    started_at,
                    float(s_sec or 0),
                    float(e_sec) if e_sec is not None else None,
                    clip_suffix,
                    expect_srt=expect_srt_subs,
                )

        if is_clip_job and subtitles:
            def _sub_watcher():
                while not sub_watcher_stop.wait(0.08):
                    _try_sync_subs()

            threading.Thread(target=_sub_watcher, daemon=True).start()

        for raw in proc.stdout:
            with lock:
                if jobs.get(jid, {}).get("state") == "Cancelled":
                    terminate_process(proc)
                    break
            line = raw.strip()
            if not line:
                continue
            recent = (recent + [line])[-15:]

            m_pl = re.search(r"\[download\] Downloading (?:item|video)\s+(\d+)\s+of\s+(\d+)", line, re.I)
            if m_pl:
                pl_idx, pl_total = int(m_pl.group(1)), int(m_pl.group(2))
                stream_count = 0
                media_phase_started = False
                update(
                    jid,
                    playlist_index=pl_idx,
                    playlist_total=pl_total,
                    playlist_done=max(0, pl_idx - 1),
                    playlist_left=max(0, pl_total - pl_idx),
                    percent=0,
                    indeterminate=False,
                    speed="",
                    eta="",
                    stage=f"Video {pl_idx}/{pl_total}",
                    title=f"Downloading video {pl_idx} of {pl_total}…",
                    detail=line[:600],
                )
                continue

            for pat, inc in (
                (r"\[download\] Destination:\s+(.+)$", 1),
                (r'\[Merger\] Merging formats into "(.+?)"', 0),
                (r"\[ExtractAudio\] Destination:\s+(.+)$", 0),
                (r"\[VideoRemuxer\] Remuxing video from \w+ to \w+; Destination:\s+(.+)$", 0),
                (r"\[download\]\s+(.+?)\s+has already been downloaded", 0),
            ):
                m = re.search(pat, line)
                if m:
                    candidate_file = m.group(1).strip().strip('"')
                    if Path(candidate_file).suffix.lower() not in SUB_OR_THUMB_EXTS:
                        saved_file = candidate_file
                        media_phase_started = True
                        stream_count += inc
                        if inc > 0:
                            clip_started_ts = time.time()

            prog = re.search(
                r"\[download\]\s+([\d.]+)%(?:\s+of\s+~?\s*[\d.]+\s*\w+)?(?:\s+at\s+(?:([\d.]+\s*\w+/s)|Unknown\s*\w*/s))?(?:\s+ETA\s+([\d:]+))?",
                line,
            )
            dl_elapsed = re.search(
                r"\[download\]\s+([\d.]+\s*\w+)(?:\s+at\s+([\d.]+\s*\w+/s))?\s+\((\d{2}):(\d{2}):(\d{2})\)",
                line,
            )
            ff_prog = re.search(r"time=(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)", line)
            if (
                ff_prog
                or dl_elapsed
                or "Input #0," in line
                or "Output #0," in line
                or "Downloading 1 time ranges" in line
                or "[Merger]" in line
                or "Merging formats" in line
                or "[EmbedSubtitle]" in line
            ):
                media_phase_started = True

            if is_clip_job and subtitles:
                _try_sync_subs()

            kw = {"detail": line[:600]}

            if prog:
                pct = float(prog.group(1))
                base_label = (
                    "Cutting & downloading clip"
                    if is_clip_job
                    else ("Downloading audio" if fmt_choice in {"mp3", "m4a", "wav"} else ("Downloading video" if stream_count <= 1 else "Downloading audio track"))
                )
                stage_label = f"Video {pl_idx}/{pl_total}" if pl_total > 1 else ("Cutting clip" if is_clip_job else base_label)
                kw.update(
                    percent=pct,
                    indeterminate=False,
                    speed=(prog.group(2) or "").strip(),
                    eta=(prog.group(3) or "").strip(),
                    stage=stage_label,
                    title=f"{base_label} ({pct:.0f}%)" + (f" [{pl_idx}/{pl_total}]" if pl_total > 1 else ""),
                )
            elif dl_elapsed:
                sp_str = (dl_elapsed.group(2) or "").strip()
                cur_sec = int(dl_elapsed.group(3)) * 3600 + int(dl_elapsed.group(4)) * 60 + int(dl_elapsed.group(5))
                if clip_duration > 0 and cur_sec > 0:
                    pct = min(99.0, max(1.0, (cur_sec / clip_duration) * 100.0))
                    wall_elapsed = max(0.5, time.time() - clip_started_ts)
                    rate = cur_sec / wall_elapsed
                    eta_str = format_seconds(int(max(0.0, clip_duration - cur_sec) / rate)) if rate > 0 else ""
                    kw.update(
                        percent=pct,
                        indeterminate=False,
                        speed=sp_str,
                        eta=eta_str,
                        stage="Cutting clip",
                        title=f"Cutting & downloading clip ({pct:.0f}%)",
                    )
                else:
                    kw.update(
                        indeterminate=True,
                        speed=sp_str,
                        eta="",
                        stage="Cutting clip",
                        title=f"Cutting clip ({format_seconds(cur_sec)} processed)…",
                    )
            elif ff_prog and is_clip_job:
                cur_sec = int(ff_prog.group(1)) * 3600 + int(ff_prog.group(2)) * 60 + float(ff_prog.group(3))
                sp_match = re.search(r"speed=\s*([\d.]+)x", line)
                sp_val = float(sp_match.group(1)) if sp_match else 0.0
                sp_str = f"{sp_val:.1f}x" if sp_val > 0 else ""
                if clip_duration > 0:
                    pct = min(99.0, max(1.0, (cur_sec / clip_duration) * 100.0))
                    eta_str = format_seconds(int(max(0.0, clip_duration - cur_sec) / sp_val)) if sp_val > 0 else ""
                    kw.update(
                        percent=pct,
                        indeterminate=False,
                        speed=sp_str,
                        eta=eta_str,
                        stage="Cutting clip",
                        title=f"Cutting & encoding clip ({pct:.0f}%)",
                    )
                else:
                    kw.update(
                        indeterminate=True,
                        speed=sp_str,
                        eta="",
                        stage="Cutting clip",
                        title=f"Cutting clip ({format_seconds(int(cur_sec))} processed)…",
                    )

            if "Merging formats" in line or "[Merger]" in line:
                kw.update(title="Merging video & audio (almost done)…", stage="Merging", speed="", eta="", indeterminate=True)
            elif "[ExtractAudio]" in line:
                kw.update(title="Converting audio format…", stage="Converting audio", speed="", eta="", indeterminate=True)
            elif "Writing video subtitles" in line or "[SubtitlesConvertor]" in line or "[EmbedSubtitle]" in line:
                kw.update(title="Processing & embedding subtitles (CC)…", stage="Subtitles (CC)", speed="", eta="", indeterminate=True)
            elif "Downloading video thumbnail" in line or "[ThumbnailsConvertor]" in line or "[EmbedThumbnail]" in line:
                kw.update(title="Embedding cover art / thumbnail…", stage="Embedding cover", speed="", eta="", indeterminate=True)

            if saved_file:
                kw["file_path"] = saved_file
            update(jid, **kw)

        rc = proc.wait()
        sub_watcher_stop.set()
        with lock:
            procs.pop(jid, None)
            job_snapshot = dict(jobs.get(jid, {}))
            is_cancelled = job_snapshot.get("state") == "Cancelled"

        if is_cancelled:
            cleanup_partial_files(out, started_at, saved_file, is_clip_job)
            update(jid, state="Cancelled", title="Download cancelled", detail="Download cancelled and temporary files cleaned up.", percent=0, indeterminate=False, speed="", eta="", stage="Cancelled")
        elif rc == 0 or (saved_file and Path(saved_file).is_file() and Path(saved_file).stat().st_size > 0):
            # Note: If --ignore-errors was active (e.g., optional subtitle track returned 429)
            # yt-dlp may exit with non-zero even though the main video file was downloaded and merged cleanly.
            final_name = Path(saved_file).name if saved_file else ""
            if final_name and (not job_snapshot.get("video_title_locked") or not allow_playlist):
                clean_title = re.sub(r"\s*\[[A-Za-z0-9_-]{3,}\](?:\s*\[clip [^\]]+\])?\.[A-Za-z0-9]+$", "", final_name)
                if clean_title and pl_total <= 1:
                    update(jid, video_title=clean_title)
            done_overrides = {}
            if pl_total > 1:
                done_overrides = {"playlist_index": pl_total, "playlist_done": pl_total, "playlist_left": 0}
            detail_msg = (
                f"Saved {pl_total} playlist items to: {out}"
                if pl_total > 1
                else (f"Saved: {final_name}" if final_name else f"Saved to: {out}")
            )
            update(
                jid,
                state="Complete",
                title="Download complete!",
                detail=detail_msg,
                percent=100,
                indeterminate=False,
                speed="",
                eta="",
                stage="Complete",
                folder=str(out),
                file_path=str(out) if pl_total > 1 else (saved_file or str(out)),
                **done_overrides,
            )
        else:
            raw_err = next((x for x in reversed(recent) if "ERROR:" in x), recent[-1] if recent else "Download failed.").replace("ERROR:", "").strip()
            update(jid, state="Error", title="Download failed", detail=raw_err[:600], percent=0, indeterminate=False, speed="", eta="", stage="Error")
    except Exception as e:
        sub_watcher_stop.set()
        with lock:
            procs.pop(jid, None)
        update(jid, state="Error", title="Download failed", detail=str(e)[:600], percent=0, indeterminate=False, speed="", eta="", stage="Error")
    finally:
        sub_watcher_stop.set()
        prune_jobs()


def open_in_explorer(target_path: str) -> bool:
    if not target_path:
        return False
    p = Path(target_path).expanduser()
    if not p.exists():
        p = p.parent if p.parent.exists() else p
    if not p.exists():
        return False
    try:
        resolved = p.resolve()
        if os.name == "nt":
            if resolved.is_file():
                subprocess.Popen(f'explorer.exe /select,"{resolved}"')
            else:
                os.startfile(str(resolved))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(resolved)] if resolved.is_file() else ["open", str(resolved)])
        else:
            subprocess.Popen(["xdg-open", str(resolved.parent if resolved.is_file() else resolved)])
        return True
    except Exception:
        return False


def pick_folder_dialog(initial_dir: str = "") -> str | None:
    """Open a native OS folder selection dialog without requiring Tkinter."""
    start_path = Path(initial_dir).expanduser() if initial_dir else DEFAULT_FOLDER
    if not start_path.exists():
        start_path = Path.home()
    start_str = str(start_path.resolve())

    try:
        if os.name == "nt":
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "[System.Windows.Forms.Application]::EnableVisualStyles(); "
                "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "$f.Description = 'Select Save Folder for ClipHaven'; "
                "$f.ShowNewFolderButton = $true; "
                f"$f.SelectedPath = {json.dumps(start_str)}; "
                "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                "Write-Output $f.SelectedPath }"
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Sta", "-WindowStyle", "Hidden", "-Command", ps_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            chosen = res.stdout.strip()
            return chosen if chosen else None

        if sys.platform == "darwin":
            res = subprocess.run(
                ["osascript", "-e", 'POSIX path of (choose folder with prompt "Select Save Folder for ClipHaven:")'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            chosen = res.stdout.strip()
            return chosen if chosen and res.returncode == 0 else None

        for cmd in (
            ["zenity", "--file-selection", "--directory", "--title=Select Save Folder for ClipHaven", f"--filename={start_str}/"],
            ["kdialog", "--getexistingdirectory", start_str, "--title", "Select Save Folder for ClipHaven"],
        ):
            if shutil.which(cmd[0]):
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", timeout=120)
                chosen = res.stdout.strip()
                return chosen if chosen and res.returncode == 0 else None
    except Exception:
        return None
    return None


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
            return self.json(200, {"ok": True, "version": VERSION, "author": AUTHOR, "repo_url": REPO_URL, "default_folder": str(DEFAULT_FOLDER), "ffmpeg": ffmpeg_available(), "jobs": recent_list})
        if p.path == "/api/ffmpeg":
            return self.json(200, {"ok": True, "available": ffmpeg_available()})
        if p.path == "/api/check-update":
            force = parse_qs(p.query).get("force", ["0"])[0] == "1"
            return self.json(200, check_github_update(force=force))
        if p.path == "/api/status":
            jid = parse_qs(p.query).get("id", [""])[0]
            with lock:
                data = dict(jobs[jid]) if jid in jobs else None
            return self.json(200, {"ok": True, **data}) if data else self.json(404, {"ok": False, "error": "Download job not found."})
        return self.json(404, {"ok": False, "error": "Not found."})

    def do_POST(self):
        origin = self.headers.get("Origin", "")
        if origin:
            parsed_origin = urlparse(origin)
            if parsed_origin.scheme != "http" or parsed_origin.hostname not in {"127.0.0.1", "localhost"}:
                return self.json(403, {"ok": False, "error": "Request origin not allowed."})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n > 20000:
                return self.json(413, {"ok": False, "error": "Request payload too large."})
            body = json.loads(self.rfile.read(n).decode("utf-8") if n > 0 else "{}")
            if not isinstance(body, dict):
                body = {}
        except Exception:
            return self.json(400, {"ok": False, "error": "Invalid request."})

        req_path = urlparse(self.path).path

        if req_path == "/api/info":
            url = extract_url(str(body.get("url", "")))
            if not valid_url(url):
                return self.json(400, {"ok": False, "error": "Enter a valid HTTPS link (YouTube, Facebook, Instagram, LinkedIn, TikTok, X, etc.)."})
            try:
                return self.json(200, {"ok": True, "info": fetch_video_info(url)})
            except Exception as e:
                return self.json(400, {"ok": False, "error": str(e)})

        if req_path == "/api/download":
            url = extract_url(str(body.get("url", "")))
            validated_folder = validate_folder(body.get("folder", str(DEFAULT_FOLDER)))
            if not validated_folder:
                return self.json(400, {"ok": False, "error": "Invalid save folder. Please enter an accessible folder path."})
            if not valid_url(url):
                return self.json(400, {"ok": False, "error": "Enter a valid HTTPS link (YouTube, Facebook, Instagram, LinkedIn, TikTok, X, etc.)."})
            fmt_choice = str(body.get("format", "mp4")).lower().strip()
            quality = str(body.get("quality", "best")).strip()
            if fmt_choice not in VALID_FORMATS or (fmt_choice in {"mp4", "mkv", "webm"} and quality not in VALID_QUALITIES):
                return self.json(400, {"ok": False, "error": "Choose a valid format and quality."})

            start_time, end_time = str(body.get("start_time", "")).strip(), str(body.get("end_time", "")).strip()
            s_sec = parse_timestamp(start_time) if start_time else 0
            e_sec = parse_timestamp(end_time) if end_time else None
            if (start_time and s_sec is None) or (end_time and e_sec is None):
                return self.json(400, {"ok": False, "error": "Clip time must be in MM:SS or HH:MM:SS format (e.g. 01:20)."})
            if e_sec is not None and s_sec is not None and e_sec <= s_sec:
                return self.json(400, {"ok": False, "error": "End time must be after start time."})

            subtitles = bool(body.get("subtitles", False))
            embed_thumbnail = bool(body.get("embed_thumbnail", False))
            allow_playlist = bool(body.get("allow_playlist", False))
            playlist_items = validate_playlist_items(str(body.get("playlist_items", "")))
            if playlist_items is None:
                return self.json(400, {"ok": False, "error": "Invalid playlist video selection."})
            raw_hint = str(body.get("title_hint", "")).strip()
            try:
                duration_hint = int(body.get("duration_hint", 0) or 0)
            except Exception:
                duration_hint = 0
            if duration_hint > 0 and s_sec is not None and s_sec >= duration_hint:
                return self.json(400, {"ok": False, "error": "Start time exceeds video duration."})

            jid, now = uuid.uuid4().hex, time.time()
            with lock:
                jobs[jid] = {
                    "state": "Queued",
                    "title": "Download queued",
                    "video_title": raw_hint or "Video download",
                    "video_title_locked": bool(raw_hint),
                    "url": url,
                    "format": fmt_choice.upper(),
                    "quality": "Audio" if fmt_choice in {"mp3", "m4a", "wav"} else ("Best" if quality == "best" else f"{quality}p"),
                    "detail": "Waiting to start…",
                    "percent": 0,
                    "indeterminate": False,
                    "speed": "",
                    "eta": "",
                    "stage": "Queued",
                    "playlist_index": 0,
                    "playlist_total": 0,
                    "playlist_done": 0,
                    "playlist_left": 0,
                    "folder": str(validated_folder),
                    "file_path": str(validated_folder),
                    "created_at": now,
                    "updated_at": now,
                }
            threading.Thread(
                target=download,
                args=(jid, url, str(validated_folder), quality, fmt_choice, start_time, end_time, subtitles, embed_thumbnail, allow_playlist, duration_hint, playlist_items),
                daemon=True,
            ).start()
            return self.json(202, {"ok": True, "id": jid, "folder": str(validated_folder)})

        if req_path == "/api/cancel":
            jid = str(body.get("id", "")).strip()
            with lock:
                if jid in jobs:
                    jobs[jid]["state"] = "Cancelled"
                proc = procs.get(jid)
            if proc:
                terminate_process(proc)
            return self.json(200, {"ok": True})

        if req_path == "/api/open-folder":
            target = str(body.get("path", "")).strip()
            jid = str(body.get("id", "")).strip()
            if not target and jid:
                with lock:
                    target = jobs.get(jid, {}).get("file_path") or jobs.get(jid, {}).get("folder") or ""
            return self.json(200, {"ok": True}) if open_in_explorer(target or str(DEFAULT_FOLDER)) else self.json(400, {"ok": False, "error": "Could not open folder on this system."})

        if req_path == "/api/pick-folder":
            current = str(body.get("current", "")).strip()
            chosen = pick_folder_dialog(current)
            if not chosen:
                return self.json(200, {"ok": True, "cancelled": True, "folder": ""})
            validated = validate_folder(chosen)
            if not validated:
                return self.json(400, {"ok": False, "error": "Selected folder is restricted or inaccessible."})
            return self.json(200, {"ok": True, "cancelled": False, "folder": str(validated)})

        if req_path == "/api/ffmpeg":
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
    print(f"ClipHaven v{VERSION} — Developed by {AUTHOR} ({REPO_URL})")
    print(f"Catch, keep, and enjoy your clips. Running at {url}")
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
