"""Subtitle timestamp parsing, trimming, shifting, and clip sync helpers."""
from __future__ import annotations
from pathlib import Path
import os
import re
import threading
import time

SUB_OR_THUMB_EXTS = {
    ".vtt", ".srt", ".ass", ".ssa", ".ttml",
    ".srv1", ".srv2", ".srv3", ".json3", ".webp", ".jpg", ".jpeg", ".png",
}
SUB_TEXT_EXTS = {".vtt", ".srt"}
SUB_SHIFT_MARKER = "⁠"
_SUB_TS_LINE_RE = re.compile(
    r"((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})(.*)"
)
_SUB_INLINE_TS_RE = re.compile(r"<((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})>")


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


