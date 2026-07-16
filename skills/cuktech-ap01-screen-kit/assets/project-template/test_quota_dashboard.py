import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from quota_dashboard import (
    AP01_GIF_MAX_BYTES,
    Quota,
    _claude_fable_limit,
    _compact_reset_summary,
    _reset_countdown,
    render_frame,
    render_master,
    render_outputs,
)


class QuotaDashboardTests(unittest.TestCase):
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
                self.assertEqual(image.info.get("loop"), 0)
                self.assertEqual(image.info.get("duration"), 1200)
                self.assertEqual(image.n_frames, 2)
            self.assertLessEqual(gif_path.stat().st_size, AP01_GIF_MAX_BYTES)
            self.assertLessEqual(gif_path.stat().st_size, 90_000)
            with Image.open(root / "screen@2x.png") as preview:
                self.assertEqual(preview.size, (640, 480))


if __name__ == "__main__":
    unittest.main()
