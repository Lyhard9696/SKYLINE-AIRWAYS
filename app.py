
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import os
import json

ROOT = Path(__file__).resolve().parent

class SkylineHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # Map URLs to the project directory instead of the process CWD.
        raw = path.split("?", 1)[0].split("#", 1)[0]
        if raw == "/":
            raw = "/templates/index.html"
        elif raw == "/manifest.webmanifest":
            raw = "/static/manifest.webmanifest"
        elif raw == "/sw.js":
            raw = "/static/sw.js"
        return str(ROOT / raw.lstrip("/"))

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        super().end_headers()

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/health":
            payload = json.dumps({"status": "ok", "app": "SKYLINE AIRWAYS v0.2"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        return super().do_GET()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), SkylineHandler)
    print(f"SKYLINE AIRWAYS v0.2 — http://0.0.0.0:{port}")
    server.serve_forever()
