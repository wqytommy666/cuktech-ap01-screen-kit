#!/usr/bin/env python3
"""Upload or deliver an already-built AP01 image without rebuilding it."""

from __future__ import annotations

import argparse
from pathlib import Path

from ap01_custom_ota import deliver, probe_ota_url, upload_to_xiaomi
from mi_cloud import MiCloud


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--upload-only",
        action="store_true",
        help="upload through a gateway-enabled account and print the signed OTA URL",
    )
    action.add_argument("--download-only", action="store_true")
    action.add_argument("--install", action="store_true")
    parser.add_argument(
        "--ota-url",
        help="use an existing signed AP01-compatible OTA URL instead of uploading",
    )
    parser.add_argument(
        "--ota-url-file",
        type=Path,
        help="read an existing signed AP01-compatible OTA URL from a text file",
    )
    parser.add_argument(
        "--url-output",
        type=Path,
        help="with --upload-only, also write the signed OTA URL to this file",
    )
    parser.add_argument("--fds-did", help="explicit FDS-capable gateway DID")
    parser.add_argument("--fds-model", help="explicit FDS-capable gateway model")
    parser.add_argument("--timeout", type=int, default=360)
    args = parser.parse_args()
    header = args.firmware.read_bytes()[:4]
    if header != b"BFNP":
        raise SystemExit("firmware does not have an AP01 BFNP header")
    if bool(args.fds_did) != bool(args.fds_model):
        parser.error("--fds-did and --fds-model must be supplied together")
    if args.ota_url and args.ota_url_file:
        parser.error("--ota-url and --ota-url-file are mutually exclusive")
    supplied_url = args.ota_url
    if args.ota_url_file:
        supplied_url = args.ota_url_file.read_text(encoding="utf-8").strip()
        if not supplied_url:
            parser.error("--ota-url-file is empty")
    if supplied_url and args.upload_only:
        parser.error("an existing OTA URL cannot be combined with --upload-only")
    if supplied_url and (args.fds_did or args.fds_model):
        parser.error("an existing OTA URL cannot be combined with FDS device options")
    if args.url_output and not args.upload_only:
        parser.error("--url-output requires --upload-only")

    cloud = MiCloud()
    if supplied_url:
        url = supplied_url
        probe_ota_url(url)
        print("已验证外部 OTA URL 的 BFNP 文件头；跳过 FDS 上传")
    else:
        url = upload_to_xiaomi(
            cloud,
            args.firmware,
            fds_did=args.fds_did,
            fds_model=args.fds_model,
        )

    if args.upload_only:
        if args.url_output:
            args.url_output.parent.mkdir(parents=True, exist_ok=True)
            args.url_output.write_text(url + "\n", encoding="utf-8")
            print(f"OTA URL 已写入：{args.url_output}")
        print(url)
        return 0

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
