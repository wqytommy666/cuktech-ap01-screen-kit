#!/usr/bin/env python3
"""Replace a compiled LVGL PNG/GIF asset without changing AP01 image length."""

from __future__ import annotations

import argparse
import hashlib
import io
import struct
from pathlib import Path

from PIL import Image

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
GIF_MAGICS = (b"GIF87a", b"GIF89a")


def find_assets(data: bytes, kind: str) -> list[tuple[int, int]]:
    magics = [PNG_MAGIC] if kind == "png" else list(GIF_MAGICS)
    offsets: set[int] = set()
    for magic in magics:
        start = 0
        while (offset := data.find(magic, start)) >= 0:
            start = offset + 1
            if offset < 28:
                continue
            size, pointer = struct.unpack_from("<II", data, offset - 16)
            if pointer - 0xA0000000 + 0x1000 == offset:
                offsets.add(offset)
    return [(offset, struct.unpack_from("<I", data, offset - 16)[0]) for offset in sorted(offsets)]


def image_info(blob: bytes) -> tuple[str, tuple[int, int], int]:
    with Image.open(io.BytesIO(blob)) as image:
        kind = image.format.lower()
        return kind, image.size, getattr(image, "n_frames", 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("firmware", type=Path)
    parser.add_argument("replacement", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--kind", choices=["gif", "png"], default="gif")
    parser.add_argument("--index", type=int, action="append", help="asset index; may be repeated")
    parser.add_argument("--all-pets", action="store_true", help="replace all five 320x240 virtual-character GIFs")
    args = parser.parse_args()

    source = bytearray(args.firmware.read_bytes())
    replacement = args.replacement.read_bytes()
    replacement_kind, replacement_size, frames = image_info(replacement)
    if replacement_kind != args.kind:
        raise SystemExit(f"replacement is {replacement_kind}, expected {args.kind}")

    assets = find_assets(source, args.kind)
    indices = list(args.index or [])
    if args.all_pets:
        if args.kind != "gif":
            raise SystemExit("--all-pets is valid only for GIF assets")
        indices.extend(range(5))
    indices = sorted(set(indices))
    if not indices:
        raise SystemExit("specify --index N or --all-pets")

    for index in indices:
        try:
            offset, capacity = assets[index]
        except IndexError:
            raise SystemExit(f"asset index {index} does not exist") from None
        with Image.open(io.BytesIO(source[offset : offset + capacity])) as original:
            original_size = original.size
        if replacement_size != original_size:
            raise SystemExit(
                f"asset {index} is {original_size[0]}x{original_size[1]}, "
                f"replacement is {replacement_size[0]}x{replacement_size[1]}"
            )
        if len(replacement) > capacity:
            raise SystemExit(
                f"replacement ({len(replacement)} bytes) exceeds asset {index} capacity ({capacity} bytes)"
            )
        source[offset : offset + capacity] = replacement + bytes(capacity - len(replacement))
        # LVGL v9 lv_image_dsc_t starts 28 bytes before the data. data_size is
        # at descriptor + 12, i.e. asset offset - 16.
        struct.pack_into("<I", source, offset - 16, len(replacement))
        print(
            f"patched {args.kind}[{index}] at 0x{offset:x}: "
            f"{capacity} -> {len(replacement)} bytes, {frames} frame(s)"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(source)
    print(f"output: {args.output}")
    print(f"size: {len(source)}")
    print(f"md5: {hashlib.md5(source).hexdigest()}")
    print(f"sha256: {hashlib.sha256(source).hexdigest()}")


if __name__ == "__main__":
    main()
