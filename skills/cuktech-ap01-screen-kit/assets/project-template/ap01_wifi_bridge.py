#!/usr/bin/env python3
"""Serve Claude/Codex quota data to a locally modified AP01 over Wi-Fi.

The stock AP01 firmware has no arbitrary-content MiOT property.  This bridge is
the LAN half of the custom-firmware design: a modified AP01 can fetch either a
compact JSON document or the already rendered 320x240 PNG/GIF.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import socket
import subprocess
import threading
import time
from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from quota_dashboard import fetch_claude_desktop, fetch_codex, render_outputs


HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
PNG = ARTIFACTS / "quota-dashboard.png"
GIF = ARTIFACTS / "quota-dashboard.gif"
MASTER = ARTIFACTS / "quota-dashboard-master.png"
JSON_OUT = ARTIFACTS / "quota-current.json"


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.last_refresh: float | None = None
        self.error: str | None = None


STATE = State()


def refresh() -> dict[str, object]:
    """Refresh both official accounts and atomically replace public artifacts."""
    claude = fetch_claude_desktop()
    codex = fetch_codex()
    temporary_png = PNG.with_name(PNG.name + ".tmp")
    temporary_gif = GIF.with_name(GIF.name + ".tmp")
    temporary_master = MASTER.with_name(MASTER.name + ".tmp")
    render_outputs(
        claude,
        codex,
        temporary_png,
        temporary_gif,
        temporary_master,
    )
    document: dict[str, object] = {
        "schema": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "claude": asdict(claude) | {"remaining_percent": claude.remaining_percent},
        "codex": asdict(codex) | {"remaining_percent": codex.remaining_percent},
    }
    temporary = JSON_OUT.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary_png.replace(PNG)
    temporary_gif.replace(GIF)
    temporary_master.replace(MASTER)
    temporary.replace(JSON_OUT)
    with STATE.lock:
        STATE.last_refresh = time.time()
        STATE.error = None
    return document


def _refresh_loop(interval: int) -> None:
    # main() performs the first refresh.  Delaying here also makes
    # --no-initial-refresh genuinely serve the last known-good snapshot.
    time.sleep(interval)
    while True:
        try:
            refresh()
        except Exception as exc:
            with STATE.lock:
                STATE.error = str(exc)
        time.sleep(interval)


def _content(path: str) -> tuple[Path, str] | None:
    return {
        "/api/v1/quota": (JSON_OUT, "application/json; charset=utf-8"),
        "/screen.png": (PNG, "image/png"),
        "/screen.gif": (GIF, "image/gif"),
    }.get(path)


class Handler(BaseHTTPRequestHandler):
    server_version = "AP01QuotaBridge/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        if self.path == "/health":
            with STATE.lock:
                body = json.dumps(
                    {
                        "ok": STATE.error is None,
                        "last_refresh": STATE.last_refresh,
                        "error": STATE.error,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode()
            self._send(body, "application/json; charset=utf-8")
            return
        item = _content(self.path)
        if item is None or not item[0].is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        path, content_type = item
        self._send(path.read_bytes(), content_type)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib callback name
        item = _content(self.path)
        if item is None or not item[0].is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        path, content_type = item
        self._send(path.read_bytes(), content_type, include_body=False)

    def _send(self, body: bytes, content_type: str, include_body: bool = True) -> None:
        etag = '"' + hashlib.sha256(body).hexdigest() + '"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("ETag", etag)
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")


def lan_ip() -> str:
    # A VPN can own the default route while the AP01 remains on Wi-Fi.  Prefer
    # macOS's physical Wi-Fi address so the printed URL is reachable by AP01.
    for interface in ("en0", "en1"):
        try:
            result = subprocess.run(
                ["ipconfig", "getifaddr", interface],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            candidate = result.stdout.strip()
            if candidate and ipaddress.ip_address(candidate).is_private:
                return candidate
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 80))
        return str(sock.getsockname()[0])
    finally:
        sock.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--interval", type=int, default=300, help="refresh interval in seconds")
    parser.add_argument("--once", action="store_true", help="refresh once and exit")
    parser.add_argument("--no-initial-refresh", action="store_true")
    args = parser.parse_args()

    if not args.no_initial_refresh:
        try:
            refresh()
        except Exception as exc:
            with STATE.lock:
                STATE.error = str(exc)
            if not all(path.is_file() for path in (PNG, GIF, JSON_OUT)):
                raise
    if args.once:
        print(JSON_OUT)
        return 0

    thread = threading.Thread(target=_refresh_loop, args=(args.interval,), daemon=True)
    thread.start()
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"AP01 quota bridge: http://{lan_ip()}:{args.port}/api/v1/quota")
    print(f"AP01 screen GIF:   http://{lan_ip()}:{args.port}/screen.gif")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
