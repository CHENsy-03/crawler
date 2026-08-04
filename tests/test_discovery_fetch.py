import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from httpx.fetch import fetch_once


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/next")
            self.end_headers()
            return
        body = b"<html><body>ok</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        if self.path != "/stream":
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_fetch_once_returns_html():
    server = _server()
    try:
        result = fetch_once(f"http://127.0.0.1:{server.server_port}/page", timeout=5)
        assert result.status_code == 200
        assert "ok" in result.text
        assert result.bytes_read > 0
        assert not result.too_large
    finally:
        server.shutdown()


def test_fetch_once_does_not_follow_redirect():
    server = _server()
    try:
        result = fetch_once(f"http://127.0.0.1:{server.server_port}/redirect", timeout=5)
        assert result.status_code == 302
        assert result.location == "/next"
    finally:
        server.shutdown()


def test_fetch_once_streaming_limit_with_content_length():
    server = _server()
    try:
        result = fetch_once(f"http://127.0.0.1:{server.server_port}/page", timeout=5, max_bytes=8)
        assert result.too_large
        assert result.bytes_read <= 8
    finally:
        server.shutdown()


def test_fetch_once_streaming_limit_without_content_length():
    server = _server()
    try:
        result = fetch_once(f"http://127.0.0.1:{server.server_port}/stream", timeout=5, max_bytes=8)
        assert result.too_large
        assert result.bytes_read > 8
    finally:
        server.shutdown()
