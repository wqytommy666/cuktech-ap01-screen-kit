from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory


class WiFiBridgeTests(unittest.TestCase):
    def test_bridge_serves_health_and_placeholder_before_live_refresh(self) -> None:
        root = Path(__file__).resolve().parent
        with TemporaryDirectory() as directory:
            try:
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    port = sock.getsockname()[1]
            except PermissionError:
                self.skipTest("local listening sockets are disabled in this sandbox")

            env = os.environ.copy()
            env["CUKTECH_ARTIFACTS_DIR"] = directory
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(root / "ap01_wifi_bridge.py"),
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--interval",
                    "600",
                    "--no-initial-refresh",
                ],
                cwd=root,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                deadline = time.monotonic() + 8
                health = None
                while time.monotonic() < deadline:
                    try:
                        with opener.open(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                            health = json.load(response)
                        break
                    except OSError:
                        time.sleep(0.1)
                self.assertIsNotNone(health, process.stderr.read() if process.poll() is not None else "")
                self.assertTrue(health["snapshot_ready"])
                self.assertFalse(health["connected"])
                self.assertEqual(health["status"], "disconnected")

                with opener.open(f"http://127.0.0.1:{port}/screen.gif", timeout=2) as response:
                    payload = response.read()
                self.assertTrue(payload.startswith(b"GIF89a"))
                self.assertLessEqual(len(payload), 90_000)
                with opener.open(f"http://127.0.0.1:{port}/api/v1/quota", timeout=2) as response:
                    document = json.load(response)
                self.assertEqual(document["status"], "disconnected")
                self.assertEqual(document["message"], "未连接，请连接")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                if process.stderr is not None:
                    process.stderr.close()


if __name__ == "__main__":
    unittest.main()
