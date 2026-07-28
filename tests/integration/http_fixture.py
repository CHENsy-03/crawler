"""Local HTTP test server for controlled response fixtures."""
import http.server
import threading
import time


class _Handler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/article/1":
            self._send(200, "<html><body><h1>Policy Title A</h1><p>Content content content content content content content content content content content content content content content content content content content content</p></body></html>")
        elif self.path == "/article/2":
            self._send(200, "<html><body><h1>Policy Title B</h1><p>Content B Content B Content B Content B Content B Content B Content B Content B Content B Content B Content B Content B Content B</p></body></html>")
        elif self.path == "/article/error":
            self.send_response(500)
            self.end_headers()
        elif self.path == "/article/error2":
            self.send_response(500)
            self.end_headers()
        elif self.path == "/article/timeout":
            time.sleep(30)
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *a):
        pass


def start_test_server(host="127.0.0.1", port=18080):
    """Start a test HTTP server in a daemon thread. Returns the server."""
    server = http.server.HTTPServer((host, port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
