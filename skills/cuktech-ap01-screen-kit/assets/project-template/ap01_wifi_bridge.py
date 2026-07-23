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
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from quota_dashboard import (
    fetch_claude_desktop,
    fetch_codex,
    render_connection_status_outputs,
    render_outputs,
)


HERE = Path(__file__).resolve().parent
ARTIFACTS = Path(os.environ.get("CUKTECH_ARTIFACTS_DIR", HERE / "artifacts"))
PNG = ARTIFACTS / "quota-dashboard.png"
GIF = ARTIFACTS / "quota-dashboard.gif"
MASTER = ARTIFACTS / "quota-dashboard-master.png"
JSON_OUT = ARTIFACTS / "quota-current.json"


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.publish_lock = threading.Lock()
        self.last_refresh: float | None = None
        self.last_attempt: float | None = None
        self.error: str | None = None
        self.refreshing = False
        self.screen_status = "starting"
        self.stale_after = 420


STATE = State()


def _fetch_with_retry(label: str, callback, attempts: int = 3):
    """Retry transient failures before publishing the disconnected screen."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return callback()
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            delay = attempt * 3
            print(f"{label} refresh failed ({attempt}/{attempts}): {exc}; retry in {delay}s")
            time.sleep(delay)
    assert last_error is not None
    raise last_error


def refresh() -> dict[str, object]:
    """Refresh both official accounts and atomically replace public artifacts."""
    with STATE.lock:
        STATE.refreshing = True
        STATE.last_attempt = time.time()
    try:
        claude = _fetch_with_retry("Claude", fetch_claude_desktop)
        codex = _fetch_with_retry("Codex", fetch_codex)
        temporary_png = PNG.with_name(PNG.name + ".tmp")
        temporary_gif = GIF.with_name(GIF.name + ".tmp")
        temporary_master = MASTER.with_name(MASTER.name + ".tmp")
        refreshed_at = datetime.now().astimezone()
        document: dict[str, object] = {
            "schema": 1,
            "generated_at": refreshed_at.isoformat(timespec="seconds"),
            "status": "live",
            "claude": asdict(claude) | {"remaining_percent": claude.remaining_percent},
            "codex": asdict(codex) | {"remaining_percent": codex.remaining_percent},
        }
        temporary = JSON_OUT.with_suffix(".json.tmp")
        with STATE.publish_lock:
            render_outputs(
                claude,
                codex,
                temporary_png,
                temporary_gif,
                temporary_master,
                refreshed_at=refreshed_at,
            )
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
            STATE.screen_status = "live"
        return document
    finally:
        with STATE.lock:
            STATE.refreshing = False


def _parse_timestamp(value: object) -> float | None:
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except (TypeError, ValueError):
        return None


def _publish_disconnected(reason: str, *, last_success: float | None = None) -> None:
    """Atomically replace any old quota card with a clear disconnected page."""

    if last_success is None:
        with STATE.lock:
            last_success = STATE.last_refresh
    last_success_datetime = (
        datetime.fromtimestamp(last_success).astimezone() if last_success is not None else None
    )
    temporary_png = PNG.with_name(PNG.name + ".status.tmp")
    temporary_gif = GIF.with_name(GIF.name + ".status.tmp")
    temporary_master = MASTER.with_name(MASTER.name + ".status.tmp")
    temporary_json = JSON_OUT.with_name(JSON_OUT.name + ".status.tmp")
    document: dict[str, object] = {
        "schema": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "disconnected",
        "last_success_at": (
            last_success_datetime.isoformat(timespec="seconds")
            if last_success_datetime is not None
            else None
        ),
        "message": "未连接，请连接",
    }
    with STATE.publish_lock:
        render_connection_status_outputs(
            temporary_png,
            temporary_gif,
            temporary_master,
            last_success_at=last_success_datetime,
        )
        temporary_json.write_text(
            json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        temporary_png.replace(PNG)
        temporary_gif.replace(GIF)
        temporary_master.replace(MASTER)
        temporary_json.replace(JSON_OUT)
    with STATE.lock:
        STATE.error = reason
        STATE.screen_status = "disconnected"


def _ensure_snapshot(stale_after: int) -> None:
    """Serve only a fresh live snapshot; never resurrect an ambiguous old card."""

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with STATE.lock:
        STATE.stale_after = stale_after
    if all(path.is_file() for path in (PNG, GIF, MASTER, JSON_OUT)):
        try:
            document = json.loads(JSON_OUT.read_text(encoding="utf-8"))
            status = str(document.get("status") or "live")
            last_success = _parse_timestamp(
                document.get("last_success_at") or document.get("generated_at")
            )
            with STATE.lock:
                STATE.last_refresh = last_success
            if status == "disconnected":
                with STATE.lock:
                    STATE.error = "等待 Claude / Codex 恢复连接"
                    STATE.screen_status = "disconnected"
                return
            if last_success is not None and time.time() - last_success <= stale_after:
                with STATE.lock:
                    STATE.error = None
                    STATE.screen_status = "live"
                return
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        _publish_disconnected("本地额度数据已超过有效期", last_success=STATE.last_refresh)
        return

    _publish_disconnected("等待 Claude / Codex 首次成功刷新")


def _refresh_once() -> None:
    try:
        refresh()
    except Exception as exc:
        _publish_disconnected(str(exc))
        print(f"Quota refresh failed; showing disconnected screen: {exc}")


def _refresh_loop(interval: int, initial_delay: bool = False) -> None:
    if initial_delay:
        time.sleep(interval)
    while True:
        _refresh_once()
        time.sleep(interval)


def _disconnect_if_stale() -> None:
    with STATE.lock:
        last_refresh = STATE.last_refresh
        stale_after = STATE.stale_after
        should_replace = (
            STATE.screen_status == "live"
            and not STATE.refreshing
            and last_refresh is not None
            and time.time() - last_refresh > stale_after
        )
    if should_replace:
        _publish_disconnected(
            f"额度数据超过 {stale_after} 秒没有成功刷新",
            last_success=last_refresh,
        )


def _content(path: str) -> tuple[Path, str] | None:
    return {
        "/api/v1/quota": (JSON_OUT, "application/json; charset=utf-8"),
        "/screen.png": (PNG, "image/png"),
        "/screen.gif": (GIF, "image/gif"),
    }.get(path)


class Handler(BaseHTTPRequestHandler):
    server_version = "AP01QuotaBridge/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        _disconnect_if_stale()
        if self.path == "/health":
            with STATE.lock:
                age = time.time() - STATE.last_refresh if STATE.last_refresh is not None else None
                connected = STATE.screen_status == "live" and STATE.error is None
                body = json.dumps(
                    {
                        "ok": connected,
                        "connected": connected,
                        "status": STATE.screen_status,
                        "last_refresh": STATE.last_refresh,
                        "last_attempt": STATE.last_attempt,
                        "age_seconds": round(age, 1) if age is not None else None,
                        "stale_after": STATE.stale_after,
                        "error": STATE.error,
                        "refreshing": STATE.refreshing,
                        "snapshot_ready": GIF.is_file(),
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
        message = fmt % args
        if '"GET /health ' in message:
            return
        print(f"[{self.log_date_time_string()}] {self.address_string()} {message}")


def lan_ip() -> str:
    override = os.environ.get("AP01_LAN_IP", "").strip()
    try:
        if override and ipaddress.ip_address(override).is_private:
            return override
    except ValueError:
        pass

    # A VPN can own the default route while the AP01 remains on Wi-Fi. Prefer
    # macOS's physical address first, then use the portable socket route on
    # Windows/Linux.
    if sys.platform == "darwin":
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
        candidate = str(sock.getsockname()[0])
        if ipaddress.ip_address(candidate).is_private:
            return candidate
    except (OSError, ValueError):
        pass
    finally:
        sock.close()

    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidate = str(item[4][0])
            if ipaddress.ip_address(candidate).is_private:
                return candidate
    except (OSError, ValueError):
        pass
    return "127.0.0.1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--interval", type=int, default=300, help="refresh interval in seconds")
    parser.add_argument(
        "--stale-after",
        type=int,
        help="show disconnected after this many seconds without a successful refresh",
    )
    parser.add_argument("--once", action="store_true", help="refresh once and exit")
    parser.add_argument("--no-initial-refresh", action="store_true")
    args = parser.parse_args()

    if args.once:
        try:
            refresh()
            print(JSON_OUT)
            return 0
        except Exception as exc:
            print(f"Quota refresh failed: {exc}")
            return 1

    stale_after = args.stale_after or max(args.interval + 120, round(args.interval * 1.4))
    if stale_after < 90:
        parser.error("--stale-after must be at least 90 seconds")
    _ensure_snapshot(stale_after)
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"AP01 quota bridge: http://{lan_ip()}:{args.port}/api/v1/quota")
    print(f"AP01 screen GIF:   http://{lan_ip()}:{args.port}/screen.gif")
    print("Bridge is ready; live account refresh continues in the background")
    thread = threading.Thread(
        target=_refresh_loop,
        args=(args.interval, args.no_initial_refresh),
        daemon=True,
    )
    thread.start()
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
