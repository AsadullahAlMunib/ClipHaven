import sys
import json
import time
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


def test_extract_and_valid_url():
    assert server.valid_url("https://www.youtube.com/watch?v=abc")
    assert server.valid_url("https://youtu.be/abc")
    assert server.valid_url("Check out this video: https://fb.watch/xyz123/!")
    assert server.valid_url("https://www.instagram.com/reel/abc123/")
    assert server.valid_url("https://www.threads.net/@user/post/abc123")
    assert server.valid_url("https://www.threads.com/@user/post/abc123")
    assert server.valid_url("https://www.linkedin.com/posts/user_activity-123456789-abcd")
    assert server.valid_url("https://www.linkedin.com/feed/update/urn:li:activity:123456789/")
    assert server.valid_url("https://lnkd.in/dXYZ123")
    assert server.valid_url("linkedin.com/posts/user_activity-123456789-abcd")
    assert server.valid_url("https://www.tiktok.com/@user/video/123456")
    assert server.valid_url("https://x.com/user/status/123456")
    assert server.valid_url("https://t.co/xyz123")
    assert server.valid_url("https://soundcloud.com/artist/track")
    assert server.valid_url("https://snd.sc/xyz123")
    assert server.valid_url("youtube.com/watch?v=abc")
    assert server.valid_url("www.youtube.com/watch?v=abc")
    assert not server.valid_url("http://youtube.com/x")
    assert not server.valid_url("https://example.com/x")
    assert server.extract_url("Watch now https://youtu.be/abc123.") == "https://youtu.be/abc123"
    assert server.extract_url("youtube.com/watch?v=abc123") == "https://youtube.com/watch?v=abc123"
    assert server._extract_yt_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123") == "dQw4w9WgXcQ"
    assert server._extract_yt_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert server._extract_yt_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_validate_folder(tmp_path):
    assert server.validate_folder(str(tmp_path)) == tmp_path
    rel_resolved = server.validate_folder("Downloads_Test_Rel")
    assert rel_resolved is not None and rel_resolved.is_absolute()
    if rel_resolved.exists():
        rel_resolved.rmdir()
    assert server.validate_folder("") is None
    assert server.validate_folder("   ") is None
    assert server.validate_folder("C:\\") is None


def test_parse_timestamp():
    assert server.parse_timestamp("01:20") == 80
    assert server.parse_timestamp("01:02:03") == 3723
    assert server.parse_timestamp("45") == 45
    assert server.parse_timestamp("01:75") is None
    assert server.parse_timestamp("invalid") is None
    assert server.parse_timestamp("") is None
    assert server.validate_playlist_items("") == ""
    assert server.validate_playlist_items("1, 3, 5-8") == "1,3,5-8"
    assert server.validate_playlist_items("1;rm -rf") is None
    assert server.is_newer_version("3.3.0", "3.2.0") is True
    assert server.is_newer_version("3.2.0", "3.2.0") is False
    assert server.is_newer_version("3.1.9", "3.2.0") is False


def test_trim_and_shift_subtitle_text_and_file(tmp_path):
    raw_vtt = """WEBVTT
Kind: captions
Language: bn

00:00:00.500 --> 00:00:04.200
আজকের ক্লাসে সবাইকে স্বাগতম

00:30:14.000 --> 00:30:18.000 align:start position:0%
Boundary cue across 30:15

00:30:20.000 --> 00:30:25.000 align:start position:0%
এখন<00:30:21.500><c> আমরা</c><00:30:23.000><c> ত্বরণ</c> নিয়ে আলোচনা করব

00:32:46.000 --> 00:32:54.000
এই অংশটি ৩২:৫০ এ শেষ হবে

00:59:58.000 --> 01:00:02.000
ধন্যবাদ সবাইকে
"""
    # Trim from 30:15 (1815s) to 32:50 (1970s) -> expected clip duration 02:35 (155s)
    shifted = server.trim_and_shift_subtitle_text(raw_vtt, 1815, 1970, is_vtt=True)
    assert "আজকের ক্লাসে সবাইকে স্বাগতম" not in shifted
    assert "ধন্যবাদ সবাইকে" not in shifted
    assert "00:00:00.000 --> 00:00:03.000" in shifted
    assert "00:00:05.000 --> 00:00:10.000" in shifted
    assert "<00:00:06.500><c> আমরা</c><00:00:08.000><c> ত্বরণ</c>" in shifted
    # End boundary cue must be clamped at 00:02:35.000 so it never stretches container duration past 02:35
    assert "00:02:31.000 --> 00:02:35.000" in shifted

    # Calling a second time must be idempotent (never double-shift)
    assert server.trim_and_shift_subtitle_text(shifted, 1815, 1970, is_vtt=True) == shifted

    # Verify expect_srt=True waits while .vtt sibling still exists (mid SubtitlesConvertor)
    vtt_file = tmp_path / "video [LNTpTCX1Crk] [clip 30-15_to_32-50].bn.vtt"
    srt_file = tmp_path / "video [LNTpTCX1Crk] [clip 30-15_to_32-50].bn.srt"
    raw_srt = """1
00:00:00,500 --> 00:00:04,200
আজকের ক্লাসে সবাইকে স্বাগতম

2
00:30:20,000 --> 00:30:25,000
এখন আমরা ত্বরণ নিয়ে আলোচনা করব

3
00:32:46,000 --> 00:32:54,000
এই অংশটি ৩২:৫০ এ শেষ হবে
"""
    vtt_file.write_text(raw_vtt, encoding="utf-8")
    srt_file.write_text(raw_srt, encoding="utf-8")
    started = time.time() - 1

    # While .vtt still exists alongside .srt and expect_srt=True, sync must wait for SubtitlesConvertor to finish
    assert server.sync_clip_subtitles_in_dir(tmp_path, started, 1815, 1970, " [clip 30-15_to_32-50]", expect_srt=True) == 0

    # Once SubtitlesConvertor deletes .vtt, sync trims and shifts .srt
    vtt_file.unlink()
    count = server.sync_clip_subtitles_in_dir(tmp_path, started, 1815, 1970, " [clip 30-15_to_32-50]", expect_srt=True)
    assert count == 1
    srt_out = srt_file.read_text(encoding="utf-8")
    assert "আজকের ক্লাসে সবাইকে স্বাগতম" not in srt_out
    assert "00:00:05,000 --> 00:00:10,000" in srt_out
    assert "00:02:31,000 --> 00:02:35,000" in srt_out
    # Second sync must skip already-shifted file
    assert server.sync_clip_subtitles_in_dir(tmp_path, started, 1815, 1970, " [clip 30-15_to_32-50]", expect_srt=True) == 0


def test_cancel_state_protection():
    server.jobs["test_cancel_jid"] = {"state": "Cancelled", "title": "Download cancelled"}
    server.update("test_cancel_jid", state="Downloading", title="Should not overwrite")
    assert server.jobs["test_cancel_jid"]["state"] == "Cancelled"
    assert server.jobs["test_cancel_jid"]["title"] == "Download cancelled"
    server.jobs.pop("test_cancel_jid", None)


def test_config_logo_and_validation_endpoints(tmp_path):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/config", timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data["version"] == "3.2.0"
            assert "default_folder" in data
            assert "ffmpeg" in data

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/logo.svg", timeout=5) as resp:
            assert resp.status == 200
            svg_text = resp.read().decode("utf-8")
            assert "<svg" in svg_text

        # Test invalid time range rejection (start_time > end_time) on /api/download
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/download",
            data=json.dumps({
                "url": "https://www.youtube.com/watch?v=abc",
                "folder": str(tmp_path),
                "format": "mp4",
                "quality": "1080",
                "start_time": "02:00",
                "end_time": "01:00",
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "Should have returned 400"
        except urllib.error.HTTPError as e:
            assert e.code == 400
            err_data = json.loads(e.read().decode("utf-8"))
            assert err_data["ok"] is False

        # Test end_time="00:00" without start_time is rejected immediately at endpoint
        req_zero_end = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/download",
            data=json.dumps({
                "url": "https://www.youtube.com/watch?v=abc",
                "folder": str(tmp_path),
                "format": "mp4",
                "quality": "1080",
                "start_time": "",
                "end_time": "00:00",
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req_zero_end, timeout=5)
            assert False, "Should have returned 400 for end_time 00:00"
        except urllib.error.HTTPError as e:
            assert e.code == 400

        # Test start_time exceeding duration_hint is rejected with 400
        req_exceed_dur = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/download",
            data=json.dumps({
                "url": "https://www.youtube.com/watch?v=abc",
                "folder": str(tmp_path),
                "format": "mp4",
                "quality": "1080",
                "start_time": "03:00",
                "end_time": "",
                "duration_hint": 120,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req_exceed_dur, timeout=5)
            assert False, "Should have returned 400 when start_time >= duration_hint"
        except urllib.error.HTTPError as e:
            assert e.code == 400

        # Test spoofed Origin header is rejected with 403
        req_bad_origin = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/info",
            data=json.dumps({"url": "https://www.youtube.com/watch?v=abc"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:80@evil.com"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req_bad_origin, timeout=5)
            assert False, "Should have returned 403 for spoofed origin"
        except urllib.error.HTTPError as e:
            assert e.code == 403

        # Test non-dict JSON body does not crash server
        req_nondict = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/info",
            data=b"[]",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req_nondict, timeout=5)
            assert False, "Should have returned 400"
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        httpd.shutdown()
        httpd.server_close()
