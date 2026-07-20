#!/usr/bin/env python3
"""Serve a replaceable AP01 GIF over LAN without writing device Flash."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import subprocess
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


WIDTH = 320
HEIGHT = 240
RAM_GIF_MAX = 256 * 1024


def lan_ip() -> str:
    for interface in ("en0", "en1"):
        completed = subprocess.run(
            ["ipconfig", "getifaddr", interface],
            capture_output=True,
            text=True,
            check=False,
        )
        candidate = completed.stdout.strip()
        try:
            if candidate and ipaddress.ip_address(candidate).is_private:
                return candidate
        except ValueError:
            pass
    return "127.0.0.1"


def validate_gif(path: Path) -> bytes:
    from PIL import Image

    body = path.read_bytes()
    if len(body) > RAM_GIF_MAX or not body.startswith(b"GIF89a") or not body.endswith(b"\x3b"):
        raise RuntimeError("screen must be GIF89a, <=256 KiB, with a valid trailer")
    with Image.open(path) as image:
        if image.size != (WIDTH, HEIGHT) or image.n_frames < 2:
            raise RuntimeError("screen must be 320x240 with at least two frames")
    return body


def make_handler(source: Path):
    started = time.time()
    lock = threading.Lock()
    state: dict[str, object] = {"requests": 0, "last_request": None, "error": None}

    class Handler(BaseHTTPRequestHandler):
        server_version = "AP01ScreenBridge/1.0"

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                with lock:
                    document = {"ok": state["error"] is None, "uptime": int(time.time() - started)} | state
                self._send(json.dumps(document, separators=(",", ":")).encode(), "application/json")
                return
            if self.path != "/screen.gif":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                body = validate_gif(source)
                with lock:
                    state["requests"] = int(state["requests"]) + 1
                    state["last_request"] = time.time()
                    state["error"] = None
                self._send(body, "image/gif")
            except Exception as exc:
                with lock:
                    state["error"] = str(exc)
                self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))

        def do_HEAD(self) -> None:  # noqa: N802
            if self.path != "/screen.gif":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = validate_gif(source)
            self._send(body, "image/gif", include_body=False)

        def _send(self, body: bytes, content_type: str, include_body: bool = True) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("ETag", '"' + hashlib.sha256(body).hexdigest() + '"')
            self.end_headers()
            if include_body:
                self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            message = fmt % args
            if '"GET /health ' in message:
                return
            print(f"[{self.log_date_time_string()}] {self.address_string()} {message}")

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    validate_gif(args.source)
    server = ThreadingHTTPServer((args.bind, args.port), make_handler(args.source.resolve()))
    print(f"AP01 screen: http://{lan_ip()}:{args.port}/screen.gif")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
