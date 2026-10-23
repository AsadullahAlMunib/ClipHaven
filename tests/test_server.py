import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

def test_valid_url():
    assert server.valid_url("https://www.youtube.com/watch?v=abc")
    assert server.valid_url("https://youtu.be/abc")
    assert not server.valid_url("http://youtube.com/x")
    assert not server.valid_url("https://example.com/x")

def test_validate_folder(tmp_path):
    assert server.validate_folder(str(tmp_path)) == tmp_path
    assert server.validate_folder("") is None
