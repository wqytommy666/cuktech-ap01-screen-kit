#!/usr/bin/env python3
"""Normalize a still image or animation into an AP01-safe 320x240 GIF89a."""

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


def _sample_animation(frames, durations: list[int], count: int):
    """Evenly reduce an animation while preserving its approximate loop time."""
    if count >= len(frames):
        return list(frames), list(durations)
    output_frames = []
    output_durations = []
    for index in range(count):
        start = round(index * len(frames) / count)
        end = round((index + 1) * len(frames) / count)
        output_frames.append(frames[start])
        output_durations.append(sum(durations[start:max(start + 1, end)]))
    return output_frames, output_durations


def _load_frames(
    source_path: Path,
    mode: str,
    background: tuple[int, int, int],
    default_duration: int,
    maximum_frames: int,
    minimum_frame_ms: int,
    flatten: bool,
):
    """Load animation frames without allowing an oversized source to exhaust RAM."""
    from PIL import Image

    with Image.open(source_path) as source:
        source_count = int(getattr(source, "n_frames", 1))
        animated = source_count > 1 and not flatten
        if not animated:
            source.seek(0)
            return [fit_frame(source.copy(), mode, background)], [default_duration], source_count

        # Divide the source into temporal chunks.  Taking the first frame from
        # each chunk and summing its durations keeps the loop length close to
        # the original while bounding AP01 decoder work.
        count = min(source_count, maximum_frames)
        frames = []
        durations = []
        for index in range(count):
            start = round(index * source_count / count)
            end = round((index + 1) * source_count / count)
            source.seek(start)
            frames.append(fit_frame(source.copy(), mode, background))
            chunk_duration = 0
            for frame_index in range(start, max(start + 1, end)):
                source.seek(frame_index)
                chunk_duration += int(source.info.get("duration", default_duration) or default_duration)
            durations.append(max(minimum_frame_ms, min(2_000, chunk_duration)))
        return frames, durations, source_count


def build(
    source_path: Path,
    output_path: Path,
    *,
    mode: str,
    background: tuple[int, int, int],
    duration: int,
    maximum_bytes: int,
    maximum_frames: int = 8,
    minimum_frame_ms: int = 120,
    flatten: bool = False,
) -> dict[str, object]:
    from PIL import Image, ImageDraw

    if maximum_frames < 2:
        raise ValueError("maximum_frames must be at least 2")
    if minimum_frame_ms < 20:
        raise ValueError("minimum_frame_ms must be at least 20")
    source_frames, source_durations, original_source_count = _load_frames(
        source_path,
        mode,
        background,
        duration,
        maximum_frames,
        minimum_frame_ms,
        flatten,
    )
    is_source_animation = len(source_frames) > 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame_budgets = [len(source_frames)] if is_source_animation else [2]
    if is_source_animation:
        frame_budgets += [value for value in (6, 4, 2) if value < len(source_frames)]
    frame_budgets = list(dict.fromkeys(frame_budgets))

    encoded = False
    encoded_frame_count = 0
    encoded_durations: list[int] = []
    for frame_budget in frame_budgets:
        if is_source_animation:
            working_frames, working_durations = _sample_animation(
                source_frames, source_durations, frame_budget
            )
        else:
            # AP01's LVGL path is most reliable with an animated GIF89a.  Two
            # visually identical frames plus a hidden edge-pixel pulse prevent
            # Pillow from collapsing a still image into GIF87a.
            working_frames = [source_frames[0].copy(), source_frames[0].copy()]
            working_durations = [duration, duration]

        for colors in (96, 80, 72, 64, 48, 32):
            palette_sheet = Image.new("RGB", (WIDTH, HEIGHT * len(working_frames)), background)
            for index, frame in enumerate(working_frames):
                palette_sheet.paste(frame, (0, HEIGHT * index))
                ImageDraw.Draw(palette_sheet).point(
                    (index, HEIGHT * index + HEIGHT - 1), fill=(255, 255, 255)
                )
            shared_palette = palette_sheet.quantize(
                colors=colors,
                method=Image.Quantize.MEDIANCUT,
                dither=Image.Dither.NONE,
            )

            encoded_frames = []
            for index, source_frame in enumerate(working_frames):
                frame = source_frame.copy()
                ImageDraw.Draw(frame).point((index, HEIGHT - 1), fill=(255, 255, 255))
                encoded_frames.append(
                    frame.quantize(palette=shared_palette, dither=Image.Dither.NONE)
                )
            encoded_frames[0].save(
                output_path,
                format="GIF",
                save_all=True,
                append_images=encoded_frames[1:],
                loop=0,
                duration=working_durations,
                disposal=2,
                optimize=False,
            )
            if output_path.stat().st_size <= maximum_bytes:
                encoded = True
                encoded_frame_count = len(encoded_frames)
                encoded_durations = working_durations
                break
        if encoded:
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
            "source_frames": original_source_count,
            "output_frames": encoded_frame_count,
            "total_duration_ms": sum(encoded_durations),
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
    parser.add_argument("--max-frames", type=int, default=8)
    parser.add_argument("--min-frame-ms", type=int, default=120)
    parser.add_argument("--flatten", action="store_true", help="use only the first animation frame")
    args = parser.parse_args()
    result = build(
        args.source,
        args.output,
        mode=args.fit,
        background=parse_color(args.background),
        duration=args.duration,
        maximum_bytes=args.max_bytes,
        maximum_frames=args.max_frames,
        minimum_frame_ms=args.min_frame_ms,
        flatten=args.flatten,
    )
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
