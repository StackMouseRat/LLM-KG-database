from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PORT = int(os.getenv("FRONTEND_UI_PORT", "5173"))
STATIC_ROOT = Path("/app/static")
PROXY_BASE = os.getenv("FRONTEND_PROXY_URL", "http://frontend-proxy:8788").rstrip("/")
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "FrontendUI/1.0"

    def log_message(self, format: str, *args) -> None:
        return

    def do_OPTIONS(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy_request()
            return
        self.send_response(204)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy_request()
            return
        self.send_response(405)
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy_request()
            return
        self._serve_static()

    def _proxy_request(self) -> None:
        body = b""
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            body = self.rfile.read(length)

        upstream_headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
        }
        request = Request(
            f"{PROXY_BASE}{self.path}",
            data=body if self.command != "GET" else None,
            method=self.command,
            headers=upstream_headers,
        )

        try:
            with urlopen(request, timeout=600) as response:
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() in HOP_BY_HOP_HEADERS:
                        continue
                    self.send_header(key, value)
                self.end_headers()

                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            for key, value in exc.headers.items():
                if key.lower() in HOP_BY_HOP_HEADERS:
                    continue
                self.send_header(key, value)
            self.end_headers()
            if payload:
                self.wfile.write(payload)
        except URLError as exc:
            payload = json.dumps({"message": str(exc.reason)}, ensure_ascii=False).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def _serve_static(self) -> None:
        target = self.path.split("?", 1)[0]
        if target in ("", "/"):
            file_path = STATIC_ROOT / "index.html"
        else:
            candidate = (STATIC_ROOT / target.lstrip("/")).resolve()
            if not str(candidate).startswith(str(STATIC_ROOT.resolve())) or not candidate.exists() or candidate.is_dir():
                file_path = STATIC_ROOT / "index.html"
            else:
                file_path = candidate

        if not file_path.exists():
            self.send_response(404)
            self.end_headers()
            return

        content = file_path.read_bytes()
        content_type, _ = mimetypes.guess_type(str(file_path))
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"frontend ui listening on {PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
