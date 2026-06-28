"""Integration tests for realtime_server.py — spawn live server, hit endpoints."""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_PY = os.path.join(PROJECT, "integration", "realtime_server.py")


def _wait_server(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
            with urllib.request.urlopen(req, timeout=1) as r:
                if json.loads(r.read()).get("status") == "ok":
                    return True
        except Exception:
            time.sleep(0.2)
    return False


@pytest.fixture(scope="module")
def server():
    """Launch realtime_server on a free port, tear down after tests."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    kwargs = dict(stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    env = os.environ.copy()
    env.setdefault("DEEPSEEK_API_KEY", "")

    proc = subprocess.Popen(
        [sys.executable, SERVER_PY, "--port", str(port)],
        env=env, **kwargs,
    )
    ok = _wait_server(port)
    if not ok:
        out, err = proc.communicate(timeout=5)
        proc.kill()
        proc.wait()
        stderr_text = err.decode(errors='replace') if err else '(none)'
        pytest.fail(f"Server failed to start on port {port}\nstderr: {stderr_text}")

    yield port

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


class TestRealtimeHealth:

    def test_health(self, server):
        r = _get(server, "/health")
        assert r["status"] == "ok"

    def test_tm_stats(self, server):
        r = _get(server, "/tm/stats")
        assert isinstance(r, dict)

    def test_options_preflight(self, server):
        req = urllib.request.Request(
            f"http://127.0.0.1:{server}/translate", method="OPTIONS",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 204
            origin = resp.headers.get("Access-Control-Allow-Origin", "")
            assert "127.0.0.1" in origin or "localhost" in origin

    def test_cors_header(self, server):
        req = urllib.request.Request(f"http://127.0.0.1:{server}/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            origin = resp.headers.get("Access-Control-Allow-Origin", "")
            assert "127.0.0.1" in origin or "localhost" in origin


class TestRealtimeValidate:

    def test_translate_empty_text(self, server):
        r = _post_err(server, "/translate", {"text": "", "from": "en", "to": "zh-CN"})
        assert r[0] == 400

    def test_translate_missing_body(self, server):
        r = _post_err(server, "/translate", {})
        assert r[0] == 400

    def test_translate_too_long(self, server):
        r = _post_err(server, "/translate",
                       {"text": "x" * 600, "from": "en", "to": "zh-CN"})
        assert r[0] == 400

    def test_batch_missing_texts(self, server):
        r = _post_err(server, "/translate/batch", {})
        assert r[0] == 400

    def test_batch_not_array(self, server):
        r = _post_err(server, "/translate/batch",
                       {"texts": "not-an-array"})
        assert r[0] == 400

    def test_body_too_large(self, server):
        big = json.dumps({"text": "x" * (100 * 1024 + 1)}).encode()
        try:
            _send(server, "/translate", big, timeout=2)
            pytest.fail("Expected 413 Payload Too Large")
        except urllib.error.HTTPError as e:
            assert e.code == 413

    def test_not_found(self, server):
        try:
            _send(server, "/nonexistent", json.dumps({}).encode(), timeout=2)
            pytest.fail("Expected 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404


class TestDetectLang:

    def test_zh(self, server):
        r = _post(server, "/detect-lang",
                   {"texts": ["你好世界，这是中文测试"]})
        assert r.get("lang") == "zh"
        assert r.get("confidence", 0) > 0.5

    def test_en(self, server):
        r = _post(server, "/detect-lang",
                   {"texts": ["Hello world, this is an English sentence"]})
        assert r.get("lang") == "en"

    def test_ja(self, server):
        r = _post(server, "/detect-lang",
                   {"texts": ["こんにちは世界"]})
        assert r.get("lang") == "ja"

    def test_ko(self, server):
        r = _post(server, "/detect-lang",
                   {"texts": ["안녕하세요 세계"]})
        assert r.get("lang") == "ko"

    def test_ru(self, server):
        r = _post(server, "/detect-lang",
                   {"texts": ["Привет мир"]})
        assert r.get("lang") == "ru"


class TestRateLimit:

    def test_rate_limited(self, server):
        """Send enough POSTs to fill rate bucket, verify 429."""
        payload = json.dumps({"text": "t", "from": "en", "to": "zh-CN"}).encode()
        got_429 = False
        errors_ok = {400, 500, 503}  # 400=validation, 500=LLM down, 503=no key
        for _ in range(150):
            try:
                _send(server, "/translate", payload, timeout=0.5)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    got_429 = True
                    break
                if e.code not in errors_ok:
                    raise
            except (OSError, TimeoutError):
                # Connection may drop on 500; retry
                continue
        assert got_429, "Expected 429 after filling rate bucket"


# ── helpers ────────────────────────────────────────────

def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as r:
        return json.loads(r.read())


def _post(port, path, data):
    """POST and return parsed JSON (assumes 2xx)."""
    return json.loads(_send(port, path, json.dumps(data).encode(), timeout=3))


def _post_err(port, path, data):
    """POST and return (status_code, body_dict) even on errors."""
    try:
        body = _send(port, path, json.dumps(data).encode(), timeout=2)
        return (200, json.loads(body))
    except urllib.error.HTTPError as e:
        return (e.code, json.loads(e.read()))


def _send(port, path, payload, *, timeout):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()
