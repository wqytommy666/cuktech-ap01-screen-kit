#!/usr/bin/env python3
"""Deliver an already-built AP01 firmware image without rebuilding its assets."""

from __future__ import annotations

import argparse
from pathlib import Path

from ap01_custom_ota import deliver, upload_to_xiaomi
from mi_cloud import MiCloud


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--download-only", action="store_true")
    action.add_argument("--install", action="store_true")
    parser.add_argument("--timeout", type=int, default=360)
    args = parser.parse_args()
    header = args.firmware.read_bytes()[:4]
    if header != b"BFNP":
        raise SystemExit("firmware does not have an AP01 BFNP header")
    cloud = MiCloud()
    url = upload_to_xiaomi(cloud, args.firmware)
    deliver(
        cloud,
        args.firmware,
        url,
        args.timeout,
        download_only=args.download_only,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
