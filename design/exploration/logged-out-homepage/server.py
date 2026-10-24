"""Serve the standalone design exploration on loopback without a database."""

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent


class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE / "public"), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def translate_path(self, path):
        return super().translate_path(path.removeprefix("/static"))

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/", "/homepage/"):
            assets = [HERE / "public/homepage.js", HERE / "public/homepage.css"]
            version = str(max(asset.stat().st_mtime_ns for asset in assets))
            document = (
                (HERE / "index.html").read_text().replace("?v=preview", f"?v={version}")
            )
            content = document.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif path.startswith("/static/"):
            super().do_GET()
        else:
            self.send_error(404)


if __name__ == "__main__":
    port = int(os.environ.get("HOMEPAGE_PORT", "8766"))
    print(f"Homepage exploration: http://127.0.0.1:{port}/homepage/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), PreviewHandler).serve_forever()
