from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler


def send_sse(handler: BaseHTTPRequestHandler, event: str, data: object) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    handler.wfile.write(f"event: {event}\n".encode("utf-8"))
    handler.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
    handler.wfile.flush()
