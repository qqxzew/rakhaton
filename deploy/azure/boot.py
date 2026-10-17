"""Placeholder on :8000 while IRIS is being initialised, so the ingress probe passes."""
from http.server import BaseHTTPRequestHandler, HTTPServer

BODY = "<meta charset=utf-8><title>PACS Komparátor</title><h2>Inicializace demo, chvíli strpení…</h2>".encode()


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(BODY)

    def log_message(self, *a):
        pass


HTTPServer(("0.0.0.0", 8000), H).serve_forever()
