# Custom content workflow

Use this path when the user wants a logo, status board, artwork, weather page,
photo, clock face, or any screen other than the quota dashboard.

## Prepare an AP01-safe asset

```bash
.venv/bin/python ap01_prepare_screen.py INPUT OUTPUT.gif \
  --fit contain --background '#01040B'
```

Use `cover` for full-bleed artwork and `stretch` only when the source already
has a 4:3 aspect ratio. The converter emits a lightweight 320x240, looping,
two-frame GIF89a. Keep the result under 90 KB when possible; the firmware-slot
hard limit is 221445 bytes and the RAM loader limit is 256 KiB.

Check the result:

```bash
python - <<'PY'
from pathlib import Path
from PIL import Image
p=Path('OUTPUT.gif')
with Image.open(p) as im:
    print(im.size, im.n_frames, im.info.get('version'), p.stat().st_size)
PY
```

Require `(320, 240)`, at least two frames, and `GIF89a`.

## Replace content without OTA

After the real-time firmware is installed, serve a mutable file:

```bash
.venv/bin/python ap01_screen_bridge.py artifacts/screen.gif --port 8765
```

Generate to a temporary path and rename it atomically:

```bash
.venv/bin/python ap01_prepare_screen.py INPUT artifacts/screen.gif.tmp
mv artifacts/screen.gif.tmp artifacts/screen.gif
```

The AP01 requests `/screen.gif` periodically and stores it in RAM. Do not run
another OTA merely to change artwork.

## Preserve AP01 overlays

If the stock clock/date must stay visible, leave logical rows `0..39` as a
solid dark background. Keep text away from the outer 5 pixels and use large,
high-contrast type because the panel is physically low resolution.
