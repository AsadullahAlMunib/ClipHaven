"""YouTube playlist Innertube continuation and recursive JSON parsing helpers."""
from __future__ import annotations
from urllib.parse import quote
import json
import re
import threading
import urllib.request


def _format_seconds_fallback(sec: int) -> str:
    h, r = divmod(max(0, int(sec)), 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


format_seconds = _format_seconds_fallback


def _format_playlist_entry(entry: dict, idx: int) -> dict:
    edur = entry.get("duration")
    dur_str = entry.get("duration_str") or (
        edur.strip() if isinstance(edur, str) and ":" in edur else (
            format_seconds(int(edur)) if isinstance(edur, (int, float)) and edur > 0 else ""
        )
    )
    return {
        "index": idx,
        "id": str(entry.get("id") or ""),
        "title": str(entry.get("title") or f"Video {idx}"),
        "duration": dur_str,
    }



def _find_inner_continuation_token(node) -> str:
    if isinstance(node, dict):
        for key in ("token", "continuation"):
            tok = node.get(key)
            if isinstance(tok, str) and len(tok.strip()) > 12:
                return tok.strip()
        for v in node.values():
            found = _find_inner_continuation_token(v)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_inner_continuation_token(item)
            if found:
                return found
    return ""


def _parse_youtube_video_item(item: dict) -> tuple[str, str, str] | None:
    if not isinstance(item, dict):
        return None
    unwrapped = item.get("richItemRenderer", {}).get("content") if isinstance(item.get("richItemRenderer"), dict) else item
    if not isinstance(unwrapped, dict):
        return None

    # 1. Legacy shape: playlistVideoRenderer
    pvr = unwrapped.get("playlistVideoRenderer")
    if isinstance(pvr, dict):
        vid = str(pvr.get("videoId") or "").strip()
        if not vid:
            return None
        title_obj = pvr.get("title")
        title = ""
        if isinstance(title_obj, dict):
            runs = title_obj.get("runs")
            if isinstance(runs, list) and runs and isinstance(runs[0], dict):
                title = str(runs[0].get("text") or "").strip()
            if not title:
                title = str(title_obj.get("simpleText") or "").strip()
        dur = ""
        lt = pvr.get("lengthText")
        if isinstance(lt, dict):
            dur = str(lt.get("simpleText") or "").strip()
        if not dur:
            lsec = pvr.get("lengthSeconds")
            if isinstance(lsec, (int, float, str)) and str(lsec).isdigit() and int(lsec) > 0:
                dur = format_seconds(int(lsec))
        return (vid, title or "Video", dur)

    # 2. Current 2026 shape: lockupViewModel
    lvm = unwrapped.get("lockupViewModel")
    if isinstance(lvm, dict):
        vid = str(lvm.get("contentId") or "").strip()
        if not vid:
            return None
        title = (
            str(
                lvm.get("metadata", {})
                .get("lockupMetadataViewModel", {})
                .get("title", {})
                .get("content")
                or ""
            ).strip()
        )
        dur = ""
        overlays = (
            lvm.get("contentImage", {})
            .get("thumbnailViewModel", {})
            .get("overlays")
        )
        if isinstance(overlays, list):
            for ov in overlays:
                if not isinstance(ov, dict):
                    continue
                badges = ov.get("thumbnailBottomOverlayViewModel", {}).get("badges")
                if isinstance(badges, list):
                    for b in badges:
                        if not isinstance(b, dict):
                            continue
                        b_text = str(b.get("thumbnailBadgeViewModel", {}).get("text") or "").strip()
                        if ":" in b_text:
                            dur = b_text
                            break
                if not dur:
                    t_text = str(ov.get("thumbnailOverlayTimeStatusRenderer", {}).get("text", {}).get("simpleText") or "").strip()
                    if ":" in t_text:
                        dur = t_text
                if dur:
                    break
        return (vid, title or "Video", dur)
    return None


def _collect_playlist_videos_and_tokens(node, videos_out: list[tuple[str, str, str]], tokens_out: list[str]):
    if isinstance(node, dict):
        if "playlistVideoRenderer" in node or "lockupViewModel" in node:
            parsed = _parse_youtube_video_item(node)
            if parsed:
                videos_out.append(parsed)
                return
        if "continuationItemViewModel" in node or "continuationItemRenderer" in node or "nextContinuationData" in node:
            sub = node.get("continuationItemViewModel") or node.get("continuationItemRenderer") or node.get("nextContinuationData")
            tok = _find_inner_continuation_token(sub)
            if tok and tok not in tokens_out:
                tokens_out.append(tok)
            return
        priority_keys = (
            "contents",
            "twoColumnBrowseResultsRenderer",
            "singleColumnBrowseResultsRenderer",
            "tabs",
            "tabRenderer",
            "content",
            "sectionListRenderer",
            "itemSectionRenderer",
            "playlistVideoListRenderer",
            "onResponseReceivedActions",
            "onResponseReceivedEndpoints",
            "appendContinuationItemsAction",
            "reloadContinuationItemsCommand",
            "continuationItems",
            "continuationContents",
            "playlistVideoListContinuation",
            "continuations",
        )
        visited = set()
        for pk in priority_keys:
            if pk in node:
                visited.add(pk)
                _collect_playlist_videos_and_tokens(node[pk], videos_out, tokens_out)
        for k, v in node.items():
            if k not in visited:
                _collect_playlist_videos_and_tokens(v, videos_out, tokens_out)
    elif isinstance(node, list):
        for item in node:
            _collect_playlist_videos_and_tokens(item, videos_out, tokens_out)


def _extract_yt_items_and_token(items_list: list) -> tuple[list[tuple[str, str, str]], str]:
    videos: list[tuple[str, str, str]] = []
    tokens: list[str] = []
    _collect_playlist_videos_and_tokens(items_list, videos, tokens)
    return (videos, tokens[0] if tokens else "")


def _post_youtube_innertube_browse(
    payload: dict,
    api_key: str = "",
    visitor_data: str = "",
    client_version: str = "2.20261101.01.00",
    cookie_header: str = "",
) -> dict | None:
    try:
        key_param = f"&key={api_key}" if api_key else ""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://www.youtube.com",
            "Referer": "https://www.youtube.com/",
            "X-YouTube-Client-Name": "1",
            "X-YouTube-Client-Version": client_version,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        }
        if visitor_data:
            headers["X-Goog-Visitor-Id"] = visitor_data
        if cookie_header:
            headers["Cookie"] = cookie_header
        req = urllib.request.Request(
            f"https://www.youtube.com/youtubei/v1/browse?prettyPrint=false{key_param}",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None



def _fetch_youtube_playlist_direct_continuations(list_id: str, clean_url: str, stop_event: threading.Event, reported_count: int = 0, *, info_cache: dict | None = None, cache_lock: threading.Lock | None = None) -> bool:
    if not list_id or list_id.startswith("RD"):
        return False
    api_key = ""
    client_version = "2.20261101.01.00"
    visitor_data = ""
    cookies_list = ["CONSENT=YES+cb.20210328-17-p0.en+FX+410", "PREF=hl=en&gl=US"]
    pending_tokens: list[str] = []
    seen_tokens: set[str] = set()
    page1_videos: list[tuple[str, str, str]] = []

    try:
        req = urllib.request.Request(
            f"https://www.youtube.com/playlist?list={list_id}&hl=en&gl=US",
            headers={
                "Cookie": "; ".join(cookies_list),
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            for sc in resp.headers.get_all("Set-Cookie") or []:
                pair = sc.split(";", 1)[0].strip()
                if pair:
                    cookies_list.append(pair)
            if resp.status == 200:
                html = resp.read().decode("utf-8", errors="replace")
                m_key = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', html)
                if m_key:
                    api_key = m_key.group(1)
                m_ver = re.search(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([^"]+)"', html)
                if m_ver:
                    client_version = m_ver.group(1)
                m_vis = re.search(r'"VISITOR_DATA"\s*:\s*"([^"]+)"', html)
                if m_vis:
                    visitor_data = m_vis.group(1)
                for marker in ("var ytInitialData = ", 'window["ytInitialData"] = '):
                    m_idx = html.find(marker)
                    if m_idx != -1:
                        j_start = m_idx + len(marker)
                        j_end = html.find(";</script>", j_start)
                        if j_end != -1:
                            root_obj = json.loads(html[j_start:j_end].strip())
                            if not visitor_data:
                                visitor_data = str(root_obj.get("responseContext", {}).get("visitorData") or "")
                            init_tokens: list[str] = []
                            _collect_playlist_videos_and_tokens(root_obj, page1_videos, init_tokens)
                            for t in init_tokens:
                                if t not in seen_tokens:
                                    seen_tokens.add(t)
                                    pending_tokens.append(t)
                            break
    except Exception:
        pass

    if stop_event.is_set():
        return False

    cookie_str = "; ".join(cookies_list)
    if not pending_tokens:
        client_obj = {"hl": "en", "gl": "US", "clientName": "WEB", "clientVersion": client_version}
        if visitor_data:
            client_obj["visitorData"] = visitor_data
        browse_id = list_id if list_id.startswith("VL") else f"VL{list_id}"
        first_resp = _post_youtube_innertube_browse(
            {"context": {"client": client_obj}, "browseId": browse_id},
            api_key,
            visitor_data,
            client_version,
            cookie_str,
        )
        if isinstance(first_resp, dict):
            if not visitor_data:
                visitor_data = str(first_resp.get("responseContext", {}).get("visitorData") or "")
            init_tokens = []
            _collect_playlist_videos_and_tokens(first_resp, page1_videos, init_tokens)
            for t in init_tokens:
                if t not in seen_tokens:
                    seen_tokens.add(t)
                    pending_tokens.append(t)

    any_added = False
    if page1_videos:
        with cache_lock:
            cached = (info_cache or {}).get(clean_url)
            if cached and len(page1_videos) > len(cached["entries"]):
                cur_idx = len(cached["entries"])
                for vid, v_title, v_dur in page1_videos[cur_idx:]:
                    cur_idx += 1
                    cached["entries"].append({
                        "index": cur_idx,
                        "id": vid,
                        "title": v_title or f"Video {cur_idx}",
                        "duration": v_dur,
                    })
                    any_added = True
                cached["playlist_count"] = max(int(cached.get("playlist_count") or 0), len(cached["entries"]))

    pages_fetched = 0
    while pending_tokens and pages_fetched < 50 and not stop_event.is_set():
        tok = pending_tokens.pop(0)
        client_obj = {"hl": "en", "gl": "US", "clientName": "WEB", "clientVersion": client_version}
        if visitor_data:
            client_obj["visitorData"] = visitor_data
        cont_resp = _post_youtube_innertube_browse(
            {"context": {"client": client_obj}, "continuation": tok},
            api_key,
            visitor_data,
            client_version,
            cookie_str,
        )
        if not isinstance(cont_resp, dict) or stop_event.is_set():
            continue
        new_vis = str(cont_resp.get("responseContext", {}).get("visitorData") or "")
        if new_vis:
            visitor_data = new_vis
        page_videos: list[tuple[str, str, str]] = []
        next_tokens: list[str] = []
        _collect_playlist_videos_and_tokens(cont_resp, page_videos, next_tokens)
        if page_videos:
            pages_fetched += 1
            for nt in reversed(next_tokens):
                if nt not in seen_tokens:
                    seen_tokens.add(nt)
                    pending_tokens.insert(0, nt)
            with cache_lock:
                cached = (info_cache or {}).get(clean_url)
                if not cached:
                    break
                cur_idx = len(cached["entries"])
                for vid, v_title, v_dur in page_videos:
                    cur_idx += 1
                    cached["entries"].append({
                        "index": cur_idx,
                        "id": vid,
                        "title": v_title or f"Video {cur_idx}",
                        "duration": v_dur,
                    })
                    any_added = True
                cached["playlist_count"] = max(int(cached.get("playlist_count") or 0), len(cached["entries"]))
        else:
            for nt in next_tokens:
                if nt not in seen_tokens:
                    seen_tokens.add(nt)
                    pending_tokens.append(nt)

    return any_added

def fetch_youtube_playlist_page1_fast(list_id: str) -> dict | None:
    """Fast (~0.5-1.0s) Page-1 YouTube playlist preview via direct ytInitialData HTML fetch."""
    if not list_id or list_id.startswith("RD"):
        return None
    try:
        req = urllib.request.Request(
            f"https://www.youtube.com/playlist?list={quote(list_id, safe='')}&hl=en&gl=US",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "Cookie": "CONSENT=YES+cb.20210328-17-p0.en+FX+410; PREF=hl=en&gl=US",
            },
        )
        with urllib.request.urlopen(req, timeout=4.5) as resp:
            if resp.status != 200:
                return None
            html = resp.read().decode("utf-8", errors="replace")
        root_obj = None
        for marker in ("var ytInitialData = ", 'window["ytInitialData"] = '):
            m_idx = html.find(marker)
            if m_idx != -1:
                json_start = m_idx + len(marker)
                end_idx = html.find(";</script>", json_start)
                if end_idx != -1:
                    root_obj = json.loads(html[json_start:end_idx].strip())
                    break
        if not isinstance(root_obj, dict):
            return None

        videos: list[tuple[str, str, str]] = []
        tokens: list[str] = []
        _collect_playlist_videos_and_tokens(root_obj, videos, tokens)
        if not videos:
            return None

        title = (
            str(
                root_obj.get("metadata", {}).get("playlistMetadataRenderer", {}).get("title")
                or root_obj.get("microformat", {}).get("microformatDataRenderer", {}).get("title")
                or root_obj.get("header", {}).get("playlistHeaderRenderer", {}).get("title", {}).get("simpleText")
                or "YouTube Playlist"
            ).strip()
        )
        uploader = (
            str(
                root_obj.get("header", {}).get("playlistHeaderRenderer", {}).get("ownerText", {}).get("runs", [{}])[0].get("text")
                or "YouTube"
            ).strip()
        )
        reported_count = len(videos)
        num_str = str(
            root_obj.get("header", {}).get("playlistHeaderRenderer", {}).get("numVideosText", {}).get("runs", [{}])[0].get("text")
            or ""
        ).replace(",", "").strip()
        if num_str.isdigit() and int(num_str) > reported_count:
            reported_count = int(num_str)

        first_vid = videos[0][0]
        thumb = f"https://i.ytimg.com/vi/{first_vid}/hqdefault.jpg" if first_vid else ""
        entries = [
            {"id": vid, "title": vtitle or f"Video {i}", "duration_str": vdur}
            for i, (vid, vtitle, vdur) in enumerate(videos, 1)
        ]
        return {
            "_type": "playlist",
            "title": title,
            "uploader": uploader,
            "thumbnail": thumb,
            "playlist_count": max(reported_count, len(entries)),
            "entries": entries,
            "webpage_url": f"https://www.youtube.com/playlist?list={list_id}",
        }
    except Exception:
        return None
