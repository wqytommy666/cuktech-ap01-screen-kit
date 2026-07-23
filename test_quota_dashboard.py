import unittest
import os
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from quota_dashboard import (
    AP01_GIF_MAX_BYTES,
    Quota,
    _claude_fable_limit,
    _codex_command,
    _codex_executable,
    _compact_reset_summary,
    _decrypt_windows_cookie,
    _read_json_rpc,
    _reset_countdown,
    render_connection_status_outputs,
    render_frame,
    render_master,
    render_outputs,
)


class QuotaDashboardTests(unittest.TestCase):
    def test_json_rpc_pipe_reader_is_windows_compatible(self) -> None:
        class Process:
            stdout = io.StringIO(
                json.dumps({"method": "ready"}) + "\n" + json.dumps({"id": 7, "result": {"ok": True}}) + "\n"
            )

        self.assertEqual(_read_json_rpc(Process(), 7, 1)["result"], {"ok": True})

    def test_windows_batch_codex_uses_cmd_prefix(self) -> None:
        from unittest.mock import patch

        with patch("quota_dashboard.os.name", "nt"), patch.dict(
            os.environ, {"COMSPEC": "C:/Windows/System32/cmd.exe"}
        ):
            self.assertEqual(
                _codex_command("C:/Users/Test/AppData/Roaming/npm/codex.cmd"),
                [
                    "C:/Windows/System32/cmd.exe",
                    "/d",
                    "/s",
                    "/c",
                    "C:/Users/Test/AppData/Roaming/npm/codex.cmd",
                ],
            )

    def test_windows_chromium_aes_cookie_decrypts_in_memory(self) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = bytes(range(32))
        nonce = bytes(range(12))
        host = ".claude.ai"
        value = "sk-ant-session-test"
        plaintext = hashlib.sha256(host.encode()).digest() + value.encode()
        encrypted = b"v10" + nonce + AESGCM(key).encrypt(nonce, plaintext, None)
        self.assertEqual(_decrypt_windows_cookie(encrypted, host, key), value)

    def test_codex_executable_accepts_explicit_desktop_or_cli_path(self) -> None:
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            executable = Path(directory) / "codex"
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o755)
            with patch.dict(os.environ, {"CUKTECH_CODEX_BIN": str(executable)}):
                self.assertEqual(_codex_executable(), str(executable))

    def test_codex_executable_finds_windows_store_companion_binary(self) -> None:
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            executable = Path(directory) / "OpenAI/Codex/bin/codex.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"MZ")
            executable.chmod(0o755)
            with patch.dict(
                os.environ,
                {"LOCALAPPDATA": directory, "CUKTECH_CODEX_BIN": ""},
            ), patch("quota_dashboard.shutil.which", return_value=None):
                self.assertEqual(_codex_executable(), str(executable))

    def test_fable_scoped_limit_is_kept_even_when_inactive(self) -> None:
        usage = {
            "limits": [
                {
                    "kind": "weekly_scoped",
                    "group": "weekly",
                    "percent": 37,
                    "resets_at": "2026-07-16T12:00:00+00:00",
                    "scope": {"model": {"id": None, "display_name": "Fable"}},
                    "is_active": False,
                }
            ]
        }
        used, reset, label = _claude_fable_limit(usage)
        self.assertEqual(used, 37.0)
        self.assertIsNotNone(reset)
        self.assertEqual(label, "FABLE 5")

    def test_reset_countdown_is_compact(self) -> None:
        now = datetime.fromtimestamp(1_000_000).astimezone()
        self.assertEqual(_reset_countdown(1_000_000 + 90_000, now), "RESET 1D 01H")
        self.assertEqual(_reset_countdown(None, now), "NOT STARTED")

    def test_reset_times_share_one_compact_chinese_header_line(self) -> None:
        five_reset = 1_784_203_199
        weekly_reset = 1_784_684_444
        five_target = datetime.fromtimestamp(five_reset).astimezone()
        week_target = datetime.fromtimestamp(weekly_reset).astimezone()
        weekday = "一二三四五六日"[week_target.weekday()]
        claude = Quota(
            provider="CLAUDE",
            used_percent=20,
            resets_at=five_reset,
            weekly_used_percent=40,
            weekly_resets_at=weekly_reset,
        )
        self.assertEqual(
            _compact_reset_summary(claude),
            f"5时{five_target:%H:%M}｜周{weekday}{week_target:%H:%M}",
        )
        codex = Quota(
            provider="CODEX",
            used_percent=None,
            weekly_used_percent=16,
            weekly_resets_at=weekly_reset,
        )
        self.assertEqual(
            _compact_reset_summary(codex),
            f"5时活动｜周{weekday}{week_target:%H:%M}",
        )

    def test_top_overlay_band_stays_empty(self) -> None:
        claude = Quota(
            provider="CLAUDE",
            used_percent=0,
            weekly_used_percent=50,
            fable_used_percent=25,
            fable_label="FABLE 5",
        )
        codex = Quota(provider="CODEX", used_percent=None, weekly_used_percent=10)
        image = render_frame(claude, codex)
        self.assertEqual(image.size, (320, 240))
        background = image.getpixel((0, 0))
        self.assertTrue(
            all(image.getpixel((x, y)) == background for y in range(40) for x in range(320))
        )

    def test_master_is_four_times_device_resolution(self) -> None:
        claude = Quota(provider="CLAUDE", used_percent=0, weekly_used_percent=100)
        codex = Quota(provider="CODEX", used_percent=None, weekly_used_percent=16)
        master = render_master(claude, codex)
        self.assertEqual(master.size, (1280, 960))
        background = master.getpixel((0, 0))
        self.assertTrue(
            all(master.getpixel((x, y)) == background for y in range(160) for x in range(1280))
        )

    def test_ap01_gif_uses_verified_animation_container(self) -> None:
        from PIL import Image

        claude = Quota(provider="CLAUDE", used_percent=0, weekly_used_percent=100)
        codex = Quota(provider="CODEX", used_percent=None, weekly_used_percent=16)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            gif_path = root / "screen.gif"
            render_outputs(
                claude,
                codex,
                root / "screen.png",
                gif_path,
                root / "master.png",
                root / "screen@2x.png",
            )
            with Image.open(gif_path) as image:
                self.assertEqual(image.info.get("version"), b"GIF89a")
                self.assertIsNone(image.info.get("loop"))
                self.assertEqual(image.info.get("duration"), 600)
                self.assertEqual(image.n_frames, 6)
                durations = []
                for index in range(image.n_frames):
                    image.seek(index)
                    durations.append(image.info.get("duration"))
                self.assertGreaterEqual(durations[-2], 400_000)
                self.assertEqual(durations[-1], 60_000)
            self.assertLessEqual(gif_path.stat().st_size, AP01_GIF_MAX_BYTES)
            self.assertLessEqual(gif_path.stat().st_size, 90_000)
            with Image.open(root / "screen@2x.png") as preview:
                self.assertEqual(preview.size, (640, 480))

    def test_disconnected_screen_is_explicit_and_ap01_compatible(self) -> None:
        from PIL import Image

        with TemporaryDirectory() as directory:
            root = Path(directory)
            gif_path = root / "disconnected.gif"
            render_connection_status_outputs(
                root / "disconnected.png",
                gif_path,
                root / "disconnected-master.png",
                last_success_at=datetime.now().astimezone(),
                preview_2x_path=root / "disconnected@2x.png",
            )
            self.assertEqual(gif_path.read_bytes()[:6], b"GIF89a")
            self.assertLessEqual(gif_path.stat().st_size, 90_000)
            with Image.open(gif_path) as image:
                self.assertEqual(image.size, (320, 240))
                self.assertEqual(image.info.get("loop"), 0)
                self.assertGreaterEqual(image.n_frames, 2)
            with Image.open(root / "disconnected.png") as image:
                background = image.getpixel((0, 0))
                self.assertTrue(
                    all(
                        image.getpixel((x, y)) == background
                        for y in range(40)
                        for x in range(320)
                    )
                )


if __name__ == "__main__":
    unittest.main()
