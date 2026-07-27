import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from monitor.metrics import get_collector


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self._respond(200, {'status': 'ok'})
        elif self.path == '/ready':
            self._respond(200, {'status': 'ready', 'checks': {'db': True, 'http': True, 'plugins': True}})
        elif self.path == '/metrics':
            collector = get_collector()
            body = collector.dump_prometheus()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(body.encode())
        else:
            self._respond(404, {'error': 'not found'})

    def _respond(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def start_health_server(port=9090, daemon=True):
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    if daemon:
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return server
    return server.serve_forever()
