#!/usr/bin/env python3
"""Convert an image into a lightweight AP01-safe 320x240 GIF89a."""

from __future__ import annotations

import argparse
from pathlib import Path


WIDTH = 320
HEIGHT = 240
FIRMWARE_SLOT_MAX = 221_445


def parse_color(value: str) -> tuple[int, int, int]:
    from PIL import ImageColor

    return ImageColor.getrgb(value)


def fit_frame(source, mode: str, background: tuple[int, int, int]):
    from PIL import Image, ImageOps

    rgba = source.convert("RGBA")
    if mode == "stretch":
        resized = rgba.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    elif mode == "cover":
        resized = ImageOps.fit(
            rgba,
            (WIDTH, HEIGHT),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    else:
        contained = ImageOps.contain(rgba, (WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        resized = Image.new("RGBA", (WIDTH, HEIGHT), background + (255,))
        resized.alpha_composite(
            contained,
            ((WIDTH - contained.width) // 2, (HEIGHT - contained.height) // 2),
        )
    canvas = Image.new("RGB", (WIDTH, HEIGHT), background)
    canvas.paste(resized.convert("RGB"), (0, 0))
    return canvas


def build(
    source_path: Path,
    output_path: Path,
    *,
    mode: str,
    background: tuple[int, int, int],
    duration: int,
    maximum_bytes: int,
) -> dict[str, object]:
    from PIL import Image, ImageDraw

    with Image.open(source_path) as source:
        base = fit_frame(source, mode, background)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    for colors in (96, 80, 72, 64, 48, 32):
        # AP01's decoder behaves reliably with GIF89a animations.  Keep two
        # slow, visually identical frames; moving one edge pixel prevents
        # Pillow from collapsing them into a single-frame GIF87a.
        palette_source = base.copy()
        ImageDraw.Draw(palette_source).point((0, HEIGHT - 1), fill=(255, 255, 255))
        shared_palette = palette_source.quantize(
            colors=colors,
            method=Image.Quantize.MEDIANCUT,
            dither=Image.Dither.NONE,
        )
        frames = []
        for pulse_x in (0, 1):
            frame = base.copy()
            ImageDraw.Draw(frame).point((pulse_x, HEIGHT - 1), fill=(255, 255, 255))
            frames.append(frame.quantize(palette=shared_palette, dither=Image.Dither.NONE))
        frames[0].save(
            output_path,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            loop=0,
            duration=duration,
            disposal=2,
            optimize=False,
        )
        if output_path.stat().st_size <= maximum_bytes:
            break
    else:
        raise RuntimeError(
            f"unable to fit GIF below {maximum_bytes} bytes: {output_path.stat().st_size}"
        )

    with Image.open(output_path) as result:
        info = {
            "path": str(output_path.resolve()),
            "size": result.size,
            "frames": result.n_frames,
            "duration_ms": result.info.get("duration"),
            "version": (result.info.get("version") or b"").decode("ascii", "replace"),
            "bytes": output_path.stat().st_size,
            "colors": colors,
        }
    if info["size"] != (WIDTH, HEIGHT) or info["frames"] < 2 or info["version"] != "GIF89a":
        raise RuntimeError(f"invalid AP01 GIF result: {info}")
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fit", choices=("contain", "cover", "stretch"), default="contain")
    parser.add_argument("--background", default="#01040B")
    parser.add_argument("--duration", type=int, default=1200)
    parser.add_argument("--max-bytes", type=int, default=FIRMWARE_SLOT_MAX)
    args = parser.parse_args()
    result = build(
        args.source,
        args.output,
        mode=args.fit,
        background=parse_color(args.background),
        duration=args.duration,
        maximum_bytes=args.max_bytes,
    )
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
