#!/usr/bin/env python3
"""Fetch official Claude Desktop + Codex quotas and render an AP01 dashboard.

The script intentionally keeps credentials in memory.  It uses:

* Codex's local ``app-server`` API for the signed-in Codex account.
* Claude Desktop's encrypted Electron cookies for the signed-in Claude account.
* Anthropic's official ``claude.ai`` usage endpoint (the same route CodexBar uses).

No API key, access token, or browser cookie is written to the output files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import mmap
import os
import select
import sqlite3
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


WIDTH = 320
HEIGHT = 240
AP01_GIF_MAX_BYTES = 221_445
# The editable/design master is 1280x960 (4x).  The AP01 panel and GIF widget
# remain physically 320x240, so this is supersampling rather than attempting
# to feed an unsupported high-resolution GIF to the device.
MASTER_SCALE = 4
PREVIEW_SCALE = 2
CLAUDE_BASE_URL = "https://claude.ai/api"
CLAUDE_DATA_DIR = Path.home() / "Library/Application Support/Claude"
CLAUDE_APP = Path("/Applications/Claude.app")
PROVIDER_ICON_DIR = Path(__file__).resolve().parent / "reference/provider-icons"


@dataclass
class Quota:
    provider: str
    used_percent: float | None
    used: int | None = None
    limit: int | None = None
    window_minutes: int | None = None
    resets_at: int | None = None
    weekly_used_percent: float | None = None
    weekly_window_minutes: int | None = None
    weekly_resets_at: int | None = None
    fable_used_percent: float | None = None
    fable_window_minutes: int | None = None
    fable_resets_at: int | None = None
    fable_label: str | None = None
    plan: str | None = None
    source: str = "live"

    @property
    def remaining_percent(self) -> float:
        used = [value for value in (self.used_percent, self.weekly_used_percent) if value is not None]
        if not used:
            return 0.0
        return max(0.0, min(100.0, 100.0 - max(used)))


def _read_json_rpc(proc: subprocess.Popen[str], request_id: int, timeout: float) -> dict[str, Any]:
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready, _, _ = select.select([proc.stdout], [], [], min(0.5, deadline - time.monotonic()))
        if not ready:
            continue
        line = proc.stdout.readline()
        if not line:
            break
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("id") == request_id:
            return message
    raise TimeoutError(f"Codex app-server request {request_id} timed out")


def fetch_codex(timeout: float = 40.0) -> Quota:
    proc = subprocess.Popen(
        ["codex", "app-server", "--listen", "stdio://"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    assert proc.stdin is not None
    try:
        init = {
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {"name": "ap01-quota-dashboard", "version": "0.1.0"},
                "capabilities": {"experimentalApi": True},
            },
        }
        proc.stdin.write(json.dumps(init, separators=(",", ":")) + "\n")
        proc.stdin.flush()
        response = _read_json_rpc(proc, 1, timeout)
        if "error" in response:
            raise RuntimeError(response["error"])

        proc.stdin.write('{"method":"initialized","params":{}}\n')
        proc.stdin.write('{"id":2,"method":"account/rateLimits/read","params":null}\n')
        proc.stdin.flush()
        response = _read_json_rpc(proc, 2, timeout)
        if "error" in response:
            raise RuntimeError(response["error"])

        snapshot = response["result"]["rateLimits"]
        primary = snapshot.get("primary") or {}
        secondary = snapshot.get("secondary") or {}
        windows = [item for item in (primary, secondary) if item.get("usedPercent") is not None]
        session_window = next(
            (item for item in windows if (item.get("windowDurationMins") or 0) <= 24 * 60),
            None,
        )
        weekly_window = next(
            (item for item in windows if (item.get("windowDurationMins") or 0) > 24 * 60),
            None,
        )
        return Quota(
            provider="CODEX",
            used_percent=(
                float(session_window["usedPercent"]) if session_window is not None else None
            ),
            window_minutes=(
                session_window.get("windowDurationMins") if session_window is not None else None
            ),
            resets_at=session_window.get("resetsAt") if session_window is not None else None,
            weekly_used_percent=(
                float(weekly_window["usedPercent"])
                if weekly_window is not None
                else None
            ),
            weekly_window_minutes=(
                weekly_window.get("windowDurationMins") if weekly_window is not None else None
            ),
            weekly_resets_at=weekly_window.get("resetsAt") if weekly_window is not None else None,
            plan=snapshot.get("planType"),
            source="Codex app-server",
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


def _claude_chrome_version() -> str:
    """Read the Chromium version embedded in the installed Claude app."""
    framework = CLAUDE_APP / (
        "Contents/Frameworks/Electron Framework.framework/Versions/A/Electron Framework"
    )
    marker = b"Chrome/"
    try:
        with framework.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
            cursor = 0
            while True:
                cursor = data.find(marker, cursor)
                if cursor < 0:
                    break
                end = cursor + len(marker)
                while end < len(data) and (48 <= data[end] <= 57 or data[end] == ord(".")):
                    end += 1
                version = data[cursor + len(marker) : end].decode("ascii", "ignore")
                if version.count(".") == 3:
                    return version
                cursor += len(marker)
    except (OSError, ValueError):
        pass
    return "148.0.7778.271"


def _claude_user_agent() -> str:
    import plistlib

    app_version = "1.0"
    electron_version = "42.5.1"
    try:
        with (CLAUDE_APP / "Contents/Info.plist").open("rb") as stream:
            app_version = str(plistlib.load(stream).get("CFBundleShortVersionString", app_version))
        with (
            CLAUDE_APP
            / "Contents/Frameworks/Electron Framework.framework/Versions/A/Resources/Info.plist"
        ).open("rb") as stream:
            electron_version = str(plistlib.load(stream).get("CFBundleVersion", electron_version))
    except OSError:
        pass
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Claude/{app_version} Chrome/{_claude_chrome_version()} "
        f"Electron/{electron_version} Safari/537.36"
    )


def _claude_cookie_rows() -> list[tuple[str, str, str, str]]:
    """Decrypt Claude Desktop cookies; return domain/name/value/path in memory."""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:
        raise RuntimeError("cryptography is required for Claude Desktop cookies") from exc

    secret = subprocess.run(
        ["security", "find-generic-password", "-s", "Claude Safe Storage", "-w"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.rstrip("\n")
    key = hashlib.pbkdf2_hmac("sha1", secret.encode(), b"saltysalt", 1003, 16)
    database = CLAUDE_DATA_DIR / "Cookies"
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT host_key,name,value,encrypted_value,path FROM cookies "
            "WHERE host_key IN ('.claude.ai','claude.ai')"
        ).fetchall()
    finally:
        connection.close()

    result: list[tuple[str, str, str, str]] = []
    for host, name, plain, encrypted, path in rows:
        value = plain
        if not value and encrypted and encrypted[:3] in (b"v10", b"v11"):
            decryptor = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
            decoded = decryptor.update(encrypted[3:]) + decryptor.finalize()
            padding = decoded[-1]
            if not 1 <= padding <= 16 or not decoded.endswith(bytes([padding]) * padding):
                continue
            decoded = decoded[:-padding]
            host_digest = hashlib.sha256(host.encode()).digest()
            if decoded.startswith(host_digest):
                decoded = decoded[len(host_digest) :]
            try:
                value = decoded.decode()
            except UnicodeDecodeError:
                continue
        if value:
            result.append((host, name, value, path))
    if not any(name == "sessionKey" and value.startswith("sk-ant-") for _, name, value, _ in result):
        raise RuntimeError("Claude Desktop sessionKey was not found")
    return result


def _iso_timestamp(value: Any) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _claude_plan(rate_limit_tier: Any, billing_type: Any) -> str:
    tier = str(rate_limit_tier or "").lower()
    if "max_20x" in tier:
        return "MAX 20X"
    if "max_5x" in tier:
        return "MAX 5X"
    if "max" in tier:
        return "MAX"
    if "pro" in tier:
        return "PRO"
    if "team" in tier:
        return "TEAM"
    if "enterprise" in tier:
        return "ENTERPRISE"
    return str(billing_type or "CLAUDE").replace("_subscription", "").upper()


def _claude_fable_limit(usage: dict[str, Any]) -> tuple[float | None, int | None, str | None]:
    """Return Claude's model-scoped weekly promotional limit.

    Claude currently exposes Fable 5 as a ``weekly_scoped`` item in the
    official usage response's ``limits`` array.  CodexBar maps the same shape
    to its named extra-rate-window rows.  Prefer an explicitly named Fable
    entry; fall back to the first model-scoped weekly entry so future display
    names continue to work.
    """

    candidates: list[tuple[float, int | None, str]] = []
    for item in usage.get("limits") or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") != "weekly_scoped" or item.get("group") != "weekly":
            continue
        value = item.get("percent")
        if not isinstance(value, (int, float)):
            continue
        scope = item.get("scope") or {}
        model = scope.get("model") or {} if isinstance(scope, dict) else {}
        label = str(model.get("display_name") or "MODEL").strip()
        candidates.append((float(value), _iso_timestamp(item.get("resets_at")), label))
    if not candidates:
        return None, None, None
    used, reset, label = next(
        (item for item in candidates if "fable" in item[2].lower()),
        candidates[0],
    )
    return used, reset, "FABLE 5" if "fable" in label.lower() else label.upper()


def fetch_claude_desktop(timeout: float = 30.0) -> Quota:
    """Read the official Claude Desktop account's 5-hour and weekly limits."""
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("requests is required for Claude Desktop quota collection") from exc

    session = requests.Session()
    for domain, name, value, path in _claude_cookie_rows():
        session.cookies.set(name, value, domain=domain, path=path)
    headers = {
        "User-Agent": _claude_user_agent(),
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://claude.ai/",
        "Origin": "https://claude.ai",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    organizations_response = session.get(
        f"{CLAUDE_BASE_URL}/organizations", headers=headers, timeout=timeout
    )
    organizations_response.raise_for_status()
    organizations = organizations_response.json()
    if not organizations:
        raise RuntimeError("Claude Desktop account has no organization")
    organization = next(
        (item for item in organizations if "chat" in (item.get("capabilities") or [])),
        None,
    ) or next(
        (item for item in organizations if not item.get("is_api_only", False)),
        organizations[0],
    )
    organization_id = organization.get("uuid") or organization.get("id")
    usage_response = session.get(
        f"{CLAUDE_BASE_URL}/organizations/{organization_id}/usage",
        headers=headers,
        timeout=timeout,
    )
    usage_response.raise_for_status()
    usage = usage_response.json()

    account_response = session.get(f"{CLAUDE_BASE_URL}/account", headers=headers, timeout=timeout)
    account = account_response.json() if account_response.ok else {}
    memberships = account.get("memberships") or []
    membership = next(
        (
            item
            for item in memberships
            if (item.get("organization") or {}).get("uuid") == organization_id
        ),
        memberships[0] if memberships else {},
    )
    account_organization = membership.get("organization") or {}

    five_hour = usage.get("five_hour") or {}
    seven_day = usage.get("seven_day") or {}
    fable_used, fable_reset, fable_label = _claude_fable_limit(usage)
    return Quota(
        provider="CLAUDE",
        used_percent=float(five_hour.get("utilization") or 0.0),
        window_minutes=300,
        resets_at=_iso_timestamp(five_hour.get("resets_at")),
        weekly_used_percent=(
            float(seven_day["utilization"])
            if seven_day.get("utilization") is not None
            else None
        ),
        weekly_window_minutes=10_080,
        weekly_resets_at=_iso_timestamp(seven_day.get("resets_at")),
        fable_used_percent=fable_used,
        fable_window_minutes=10_080 if fable_used is not None else None,
        fable_resets_at=fable_reset,
        fable_label=fable_label,
        plan=_claude_plan(
            account_organization.get("rate_limit_tier"),
            account_organization.get("billing_type"),
        ),
        source="Claude Desktop / claude.ai",
    )


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = (
        [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/SFCompact.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        if bold
        else [
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for candidate in candidates:
        if os.path.exists(candidate):
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                pass
    return ImageFont.load_default()


def _condensed_font(size: int):
    """Return a bold condensed face for the large ring numerals.

    The AP01 only has 320 horizontal pixels.  A condensed numeric face lets a
    three-digit value such as ``100%`` remain genuinely large without crossing
    the progress ring.  The fallbacks keep rendering deterministic off macOS.
    """

    from PIL import ImageFont

    candidates = (
        "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    )
    for candidate in candidates:
        if os.path.exists(candidate):
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                pass
    return _font(size, bold=True)


def _cjk_font(size: int, bold: bool = False):
    """Return a face that contains the compact Chinese dashboard labels."""

    from PIL import ImageFont

    candidates = (
        [
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ]
        if bold
        else [
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ]
    )
    for candidate in candidates:
        if os.path.exists(candidate):
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                pass
    return _font(size, bold=bold)


def _short_number(value: int | None) -> str:
    if value is None:
        return "--"
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def _left_percent(used_percent: float | None) -> float | None:
    if used_percent is None:
        return None
    return max(0.0, min(100.0, 100.0 - used_percent))


def _reset_countdown(resets_at: int | None, now: datetime | None = None) -> str:
    if not resets_at:
        return "NOT STARTED"
    current = now or datetime.now().astimezone()
    delta = max(0, int(resets_at - current.timestamp()))
    days, remainder = divmod(delta, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes = remainder // 60
    if days:
        return f"RESET {days}D {hours:02d}H"
    if hours:
        return f"RESET {hours}H {minutes:02d}M"
    return f"RESET {minutes}M"


def _compact_reset_summary(quota: Quota) -> str:
    """Format both quota reset clocks as one short, local-time header line.

    The AP01 header has room for one line only.  A missing Codex 5-hour
    window is the account's activity/promotion state rather than an error, so
    keep the agreed ``5时活动`` wording instead of showing placeholder dashes.
    """

    if quota.resets_at:
        five_target = datetime.fromtimestamp(quota.resets_at).astimezone()
        five = f"5时{five_target:%H:%M}"
    elif quota.provider.upper() == "CODEX":
        five = "5时活动"
    else:
        five = "5时待用"

    if quota.weekly_resets_at:
        week_target = datetime.fromtimestamp(quota.weekly_resets_at).astimezone()
        weekday = "一二三四五六日"[week_target.weekday()]
        week = f"周{weekday}{week_target:%H:%M}"
    else:
        week = "周待用"
    return f"{five}｜{week}"


def render_master(claude: Quota, codex: Quota, scale: int = MASTER_SCALE):
    """Render a high-resolution vector-like master using 320x240 logical units."""

    from PIL import Image, ImageColor, ImageDraw, ImageFilter

    if scale < 1:
        raise ValueError("scale must be at least 1")

    def s(value: float) -> int:
        return int(round(value * scale))

    def sr(values: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        return tuple(s(value) for value in values)  # type: ignore[return-value]

    # AP01's panel lifts blacks and can look washed out.  Use near-black navy
    # surfaces and restrained accents so the physical display lands closer to
    # the intended OLED-style contrast.
    background = "#01040B"
    image = Image.new("RGBA", (WIDTH * scale, HEIGHT * scale), background)
    draw = ImageDraw.Draw(image)
    card_color = "#030B15"
    edge_color = "#1B2A3E"
    text_color = "#F8FAFC"
    muted_color = "#8C98AA"
    # Disabled information still needs to survive the AP01 panel's low pixel
    # density and viewing angle, so keep it clearly above the card background.
    disabled_color = "#5E6B7E"
    danger_color = "#E94F67"
    claude_color = "#F07A32"
    codex_color = "#159FCB"

    provider_font = _font(s(14), bold=True)
    plan_font = _font(s(8), bold=True)
    reset_summary_font = _cjk_font(s(10), bold=True)
    ring_label_font = _cjk_font(s(9), bold=True)
    ring_label_latin_font = _font(s(8), bold=True)
    # Large condensed numerals use almost the complete ring interior without
    # forcing the three-column Claude row to shrink.
    value_font_claude = _condensed_font(s(31))
    value_font_codex = _condensed_font(s(34))
    percent_font_claude = _condensed_font(s(13))
    percent_font_codex = _condensed_font(s(14))

    def text(
        position: tuple[float, float],
        value: str,
        face: Any,
        fill: str,
        anchor: str | None = None,
    ) -> None:
        draw.text((s(position[0]), s(position[1])), value, font=face, fill=fill, anchor=anchor)

    def blend(first: Any, second: Any, amount: float) -> tuple[int, int, int, int]:
        """Blend two opaque colours for compact OLED gradients."""

        def rgb(value: Any) -> tuple[int, int, int]:
            if isinstance(value, str):
                return ImageColor.getrgb(value)
            return tuple(value[:3])  # type: ignore[return-value]

        left = rgb(first)
        right = rgb(second)
        t = max(0.0, min(1.0, amount))
        return tuple(round(a + (b - a) * t) for a, b in zip(left, right)) + (255,)

    def gradient_round_rect(
        bounds: tuple[float, float, float, float],
        radius: float,
        top: Any,
        bottom: Any,
        outline: Any | None = None,
        outline_width: float = 1,
    ) -> None:
        """Paint a true vertical gradient clipped by a rounded rectangle."""

        x1, y1, x2, y2 = sr(bounds)
        width = max(1, x2 - x1 + 1)
        height = max(1, y2 - y1 + 1)
        gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        gradient_draw = ImageDraw.Draw(gradient)
        for row in range(height):
            amount = row / max(1, height - 1)
            gradient_draw.line((0, row, width, row), fill=blend(top, bottom, amount))
        mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, width - 1, height - 1),
            radius=s(radius),
            fill=255,
        )
        image.paste(gradient, (x1, y1), mask)
        if outline:
            draw.rounded_rectangle(
                sr(bounds),
                radius=s(radius),
                outline=outline,
                width=max(1, s(outline_width)),
            )

    def glow_panel(bounds: tuple[int, int, int, int], accent: str) -> None:
        x1, y1, x2, y2 = bounds
        shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle(
            sr((x1, y1 + 2, x2, y2 + 2)), radius=s(10), fill=(0, 0, 0, 150)
        )
        image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(s(3))))

        accent_glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        accent_draw = ImageDraw.Draw(accent_glow)
        accent_draw.rounded_rectangle(
            sr((x1 - 1, y1 + 1, x1 + 10, y2 - 1)),
            radius=s(11),
            fill=accent,
        )
        # UI/UX Pro Max: on a tiny OLED-style dashboard, restrained glow and a
        # crisp silhouette read better than a large halo.
        accent_glow = accent_glow.filter(ImageFilter.GaussianBlur(s(2.5)))
        accent_glow.putalpha(accent_glow.getchannel("A").point(lambda value: value // 3))
        image.alpha_composite(accent_glow)

        # The reference uses a coloured rounded shell behind the dark card,
        # not a flat stripe pasted on top.  Offsetting the foreground card
        # exposes the shell's large top/bottom curves and gives the rail depth.
        gradient_round_rect(
            bounds,
            radius=13,
            top=blend(accent, "#FFFFFF", 0.24),
            bottom=blend(accent, "#000000", 0.22),
        )
        gradient_round_rect(
            (x1 + 7, y1, x2, y2),
            radius=13,
            top="#061225",
            bottom=card_color,
            outline=edge_color,
        )
        # A narrow inner highlight reproduces the luminous material edge while
        # retaining enough dark separation from the content card.
        draw.rounded_rectangle(
            sr((x1 + 1.2, y1 + 8, x1 + 2.4, y2 - 8)),
            radius=s(0.7),
            fill=blend(accent, "#FFFFFF", 0.38),
        )

    def provider_icon(name: str, x: float, y: float, size: float, color: str) -> None:
        path = PROVIDER_ICON_DIR / f"{name}.png"
        if not path.exists():
            return
        target = s(size)
        with Image.open(path).convert("RGBA") as source:
            source.thumbnail((target, target), Image.Resampling.LANCZOS)
            tinted = Image.new("RGBA", source.size, color)
            tinted.putalpha(source.getchannel("A"))
            image.alpha_composite(
                tinted,
                (s(x) + (target - source.width) // 2, s(y) + (target - source.height) // 2),
            )

    def quota_ring(
        center: tuple[float, float],
        radius: float,
        used: float | None,
        label: str,
        label_face: Any,
        accent: str,
        value_face: Any,
        percent_face: Any,
    ) -> None:
        cx, cy = center
        bounds = (cx - radius, cy - radius, cx + radius, cy + radius)
        ring_width = s(4.5)
        # A slightly dimensional track prevents the low-resolution stroke from
        # looking like a hard, flat vector circle.
        draw.ellipse(sr(bounds), outline="#202C3D", width=ring_width)
        draw.arc(
            sr(bounds),
            start=205,
            end=335,
            fill="#2B3A50",
            width=ring_width,
        )
        left = _left_percent(used)
        if left is not None and left > 0:
            end = -90 + 360 * left / 100.0
            arc_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
            arc_draw = ImageDraw.Draw(arc_layer)
            span = end + 90
            segments = max(1, math.ceil(span / 2))

            def arc_colour(angle: float) -> tuple[int, int, int, int]:
                # Directional, cyclic lighting keeps a full 100% ring seamless:
                # bright at the upper-right and deep at the lower-left.
                light = (math.cos(math.radians(angle + 45)) + 1) / 2
                darkened = blend("#000000", accent, 0.62 + 0.38 * light)
                highlight = 0.10 * light**3
                white = (255, 255, 255, 255)
                return tuple(
                    round(channel + (white[index] - channel) * highlight)
                    for index, channel in enumerate(darkened)
                )  # type: ignore[return-value]

            pixel_bounds = sr(bounds)
            for index in range(segments):
                start_angle = -90 + span * index / segments
                end_angle = -90 + span * (index + 1) / segments + 0.45
                arc_draw.arc(
                    pixel_bounds,
                    start=start_angle,
                    end=end_angle,
                    fill=arc_colour((start_angle + end_angle) / 2),
                    width=ring_width,
                )

            # Pillow arcs use square caps.  Explicit endpoint discs create the
            # polished rounded caps visible in the reference design.
            if left < 99.9:
                center_x = s(cx)
                center_y = s(cy)
                # ImageDraw keeps an ellipse outline inside its bounding box,
                # so the stroke centreline is half a stroke inward.  Place the
                # cap there as well; using the outer radius creates ugly knobs.
                pixel_radius = s(radius) - ring_width / 2
                cap_radius = ring_width / 2
                for angle in (-90.0, end):
                    radians = math.radians(angle)
                    cap_x = center_x + pixel_radius * math.cos(radians)
                    cap_y = center_y + pixel_radius * math.sin(radians)
                    arc_draw.ellipse(
                        (
                            cap_x - cap_radius,
                            cap_y - cap_radius,
                            cap_x + cap_radius,
                            cap_y + cap_radius,
                        ),
                        fill=arc_colour(angle),
                    )

            glow = arc_layer.filter(ImageFilter.GaussianBlur(s(2)))
            glow.putalpha(glow.getchannel("A").point(lambda value: value * 3 // 5))
            image.alpha_composite(glow)
            image.alpha_composite(arc_layer)

        def visual_bbox(value: str, face: Any) -> tuple[int, int, int, int]:
            return draw.textbbox((0, 0), value, font=face)

        # Leave the lower third of the enlarged ring for the window label.
        # The value group is optically centred in the upper portion instead of
        # sitting on the ring's geometric midline.
        value_center_y = cy - 6

        def draw_centered(value: str, face: Any, fill: str) -> None:
            box = visual_bbox(value, face)
            visible_width = box[2] - box[0]
            visible_height = box[3] - box[1]
            draw.text(
                (
                    s(cx) - visible_width / 2 - box[0],
                    s(value_center_y) - visible_height / 2 - box[1],
                ),
                value,
                font=face,
                fill=fill,
            )

        if left is None:
            draw_centered("—", value_face, disabled_color)
            text((cx, cy + 18), label, label_face, disabled_color, "mm")
            return
        numeric = f"{left:.0f}"
        value_color = danger_color if left <= 10 else text_color
        number_box = visual_bbox(numeric, value_face)
        percent_box = visual_bbox("%", percent_face)
        number_width = number_box[2] - number_box[0]
        number_height = number_box[3] - number_box[1]
        percent_width = percent_box[2] - percent_box[0]
        percent_height = percent_box[3] - percent_box[1]
        gap = s(1)
        group_width = number_width + gap + percent_width
        # Bottom-align the small percent sign inside the number's visible box,
        # then centre the complete visible group on the ring's exact centre.
        group_left = s(cx) - group_width / 2
        group_top = s(value_center_y) - number_height / 2
        percent_top = group_top + number_height - percent_height - s(1)
        draw.text(
            (group_left - number_box[0], group_top - number_box[1]),
            numeric,
            font=value_face,
            fill=value_color,
        )
        draw.text(
            (
                group_left + number_width + gap - percent_box[0],
                percent_top - percent_box[1],
            ),
            "%",
            font=percent_face,
            fill=danger_color if left <= 10 else accent,
        )
        # Muted text provides a second, non-colour cue while keeping a clear
        # inner gap from the 5 px ring stroke at the bottom.
        text((cx, cy + 18), label, label_face, muted_color, "mm")

    def panel_header(
        bounds: tuple[int, int, int, int],
        title: str,
        plan: str,
        reset_summary: str,
        icon_name: str,
        accent: str,
    ) -> None:
        x1, y1, x2, _ = bounds
        provider_icon(icon_name, x1 + 10, y1 + 5, 15, accent)
        provider_x = x1 + 31
        center_y = y1 + 12
        text((provider_x, center_y), title, provider_font, text_color, "lm")
        provider_width = draw.textlength(title, font=provider_font) / scale
        plan_width = draw.textlength(plan, font=plan_font) / scale + 10
        badge = (
            provider_x + provider_width + 6,
            y1 + 5.5,
            provider_x + provider_width + 6 + plan_width,
            y1 + 18.5,
        )
        gradient_round_rect(
            badge,
            radius=5,
            top="#102139",
            bottom="#07101E",
            outline=blend("#16243A", accent, 0.30),
        )
        text(
            ((badge[0] + badge[2]) / 2, (badge[1] + badge[3]) / 2),
            plan,
            plan_font,
            accent,
            "mm",
        )
        text((x2 - 7, center_y), reset_summary, reset_summary_font, text_color, "rm")

    # Compact inset cards leave more breathing room around the tiny AP01 panel
    # and reduce the number of high-entropy pixels the GIF decoder processes.
    claude_bounds = (11, 43, 309, 135)
    codex_bounds = (11, 143, 309, 236)
    glow_panel(claude_bounds, claude_color)
    glow_panel(codex_bounds, codex_color)
    panel_header(
        claude_bounds,
        "CLAUDE",
        (claude.plan or "MAX").upper(),
        _compact_reset_summary(claude),
        "claude",
        claude_color,
    )
    panel_header(
        codex_bounds,
        "CODEX",
        (
            "PRO 20X"
            if (codex.plan or "PRO").upper() == "PRO"
            else (codex.plan or "PRO").upper()
        ),
        _compact_reset_summary(codex),
        "codex",
        codex_color,
    )

    claude_centers = (62, 160, 258)
    claude_windows = (
        ("5小时", claude.used_percent),
        ("本周", claude.weekly_used_percent),
        (claude.fable_label or "FABLE 5", claude.fable_used_percent),
    )
    for index, (label, used) in enumerate(claude_windows):
        cx = claude_centers[index]
        if index:
            separator_x = (claude_centers[index - 1] + cx) / 2
            draw.line(sr((separator_x, 65, separator_x, 130)), fill="#172338", width=s(1))
        label_face = (
            ring_label_latin_font if label.upper().startswith("FABLE") else ring_label_font
        )
        quota_ring(
            (cx, 100),
            30,
            used,
            label,
            label_face,
            claude_color,
            value_font_claude,
            percent_font_claude,
        )

    codex_centers = (85, 235)
    codex_windows = (
        ("5小时", codex.used_percent),
        ("本周", codex.weekly_used_percent),
    )
    for index, (label, used) in enumerate(codex_windows):
        cx = codex_centers[index]
        if index:
            draw.line(sr((160, 165, 160, 231)), fill="#172338", width=s(1))
        quota_ring(
            (cx, 201),
            30,
            used,
            label,
            ring_label_font,
            codex_color,
            value_font_codex,
            percent_font_codex,
        )

    # The AP01 firmware paints its own clock over rows 0..39.  Clear the
    # high-resolution master too, not only the downsampled device frame, so no
    # panel glow can leak into that reserved system band.
    draw.rectangle((0, 0, WIDTH * scale - 1, s(40) - 1), fill=background)
    return image.convert("RGB")


def _frame_from_master(master, output_scale: int = 1):
    from PIL import Image, ImageDraw

    if output_scale < 1:
        raise ValueError("output_scale must be at least 1")
    frame = master.resize(
        (WIDTH * output_scale, HEIGHT * output_scale),
        Image.Resampling.LANCZOS,
    )
    # Resampling can bleed the panel glow by a fraction of a pixel. Reassert
    # the AP01 system overlay's reserved top band after the resize.
    draw = ImageDraw.Draw(frame)
    draw.rectangle(
        (0, 0, WIDTH * output_scale - 1, 40 * output_scale - 1),
        fill="#01040B",
    )
    return frame


def _device_frame_from_master(master):
    return _frame_from_master(master, output_scale=1)


def render_frame(claude: Quota, codex: Quota, phase: int = 0):
    return _device_frame_from_master(render_master(claude, codex, scale=MASTER_SCALE))


def render_outputs(
    claude: Quota,
    codex: Quota,
    png_path: Path,
    gif_path: Path,
    master_path: Path,
    preview_2x_path: Path | None = None,
) -> None:
    from PIL import Image, ImageDraw

    paths = [png_path, gif_path, master_path]
    if preview_2x_path is not None:
        paths.append(preview_2x_path)
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    master = render_master(claude, codex, scale=MASTER_SCALE)
    frame = _device_frame_from_master(master)
    master.save(master_path, format="PNG", optimize=True)
    frame.save(png_path, format="PNG", optimize=True)
    if preview_2x_path is not None:
        _frame_from_master(master, output_scale=PREVIEW_SCALE).save(
            preview_2x_path,
            format="PNG",
            optimize=True,
        )
    # AP01's pet page expects an animated GIF89a; a one-frame GIF can render as
    # black.  Four low-entropy frames add a restrained travelling glint to both
    # provider rails.  Text and quota values remain fixed, so the tiny decoder
    # stays smooth while the physical display has visible life.
    pulse_phases = (0.12, 0.38, 0.66, 0.38)
    for color_count in (96, 80, 72, 64):
        shared_palette = frame.quantize(
            colors=color_count,
            method=Image.Quantize.MEDIANCUT,
            dither=Image.Dither.NONE,
        )
        gif_frames = []
        for phase in pulse_phases:
            animated = frame.copy()
            animated_draw = ImageDraw.Draw(animated)
            claude_y = 56 + round(phase * 63)
            codex_y = 150 + round(phase * 62)
            animated_draw.rounded_rectangle(
                (12, claude_y - 4, 14, claude_y + 4),
                radius=1,
                fill="#FFD09A",
            )
            animated_draw.rounded_rectangle(
                (12, codex_y - 4, 14, codex_y + 4),
                radius=1,
                fill="#7BE6FF",
            )
            gif_frames.append(
                animated.quantize(palette=shared_palette, dither=Image.Dither.NONE)
            )
        gif_frames[0].save(
            gif_path,
            format="GIF",
            save_all=True,
            append_images=gif_frames[1:],
            loop=0,
            duration=600,
            disposal=2,
            optimize=False,
        )
        if gif_path.stat().st_size <= AP01_GIF_MAX_BYTES:
            break
    else:
        raise RuntimeError(
            f"GIF exceeds AP01 slot: {gif_path.stat().st_size} > {AP01_GIF_MAX_BYTES} bytes"
        )


def _fallback(provider: str, used_percent: float) -> Quota:
    return Quota(provider=provider, used_percent=used_percent, source="fallback")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    artifacts = Path(__file__).resolve().parent / "artifacts"
    parser.add_argument("--png", type=Path, default=artifacts / "quota-dashboard.png")
    parser.add_argument("--gif", type=Path, default=artifacts / "quota-dashboard.gif")
    parser.add_argument(
        "--master",
        type=Path,
        default=artifacts / "quota-dashboard-master.png",
        help="4x 1280x960 supersampled master",
    )
    parser.add_argument(
        "--preview-2x",
        type=Path,
        default=artifacts / "quota-dashboard@2x.png",
        help="optional 640x480 design preview (not the AP01 firmware asset)",
    )
    parser.add_argument("--json-out", type=Path, default=artifacts / "quota-current.json")
    parser.add_argument("--claude-used", type=float, help="Fallback/mock Claude used percentage")
    parser.add_argument("--codex-used", type=float, help="Fallback/mock Codex used percentage")
    parser.add_argument("--no-live", action="store_true", help="Do not call live quota services")
    args = parser.parse_args()

    errors: list[str] = []
    if args.no_live:
        claude = _fallback("CLAUDE", args.claude_used if args.claude_used is not None else 20.0)
        claude.plan = "MAX"
        codex = _fallback("CODEX", args.codex_used if args.codex_used is not None else 7.0)
    else:
        try:
            claude = fetch_claude_desktop()
        except Exception as exc:  # Keep rendering even when a provider is offline.
            errors.append(f"Claude Desktop: {exc}")
            claude = _fallback("CLAUDE", args.claude_used if args.claude_used is not None else 0.0)
            claude.plan = "MAX"
        try:
            codex = fetch_codex()
        except Exception as exc:
            errors.append(f"Codex: {exc}")
            codex = _fallback("CODEX", args.codex_used if args.codex_used is not None else 0.0)

    render_outputs(
        claude,
        codex,
        args.png,
        args.gif,
        args.master,
        args.preview_2x,
    )
    document = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "claude": asdict(claude) | {"remaining_percent": claude.remaining_percent},
        "codex": asdict(codex) | {"remaining_percent": codex.remaining_percent},
        "errors": errors,
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document, ensure_ascii=False, indent=2))
    print(f"PNG: {args.png}")
    print(f"GIF: {args.gif}")
    print(f"MASTER: {args.master}")
    print(f"2X PREVIEW: {args.preview_2x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
