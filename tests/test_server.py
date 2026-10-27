import sys
import json
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
    assert server.valid_url("https://www.tiktok.com/@user/video/123456")
    assert server.valid_url("https://x.com/user/status/123456")
    assert not server.valid_url("http://youtube.com/x")
    assert not server.valid_url("https://example.com/x")
    assert server.extract_url("Watch now https://youtu.be/abc123.") == "https://youtu.be/abc123"


def test_validate_folder(tmp_path):
    assert server.validate_folder(str(tmp_path)) == tmp_path
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
            assert "default_folder" in data
            assert "ffmpeg" in data

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/logo.svg", timeout=5) as resp:
            assert resp.status == 200
            svg_text = resp.read().decode("utf-8")
            assert "<svg" in svg_text

        # Test invalid time range rejection on /api/download
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
    finally:
        httpd.shutdown()
        httpd.server_close()
