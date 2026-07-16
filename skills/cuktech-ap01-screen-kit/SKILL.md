---
name: cuktech-ap01-screen-kit
description: Create, customize, validate, deploy, and operate Wi-Fi-updated screens for the CUKTECH AP01 detachable display. Use when Codex needs to convert images or GIFs to AP01-safe content, design a custom 320x240 dashboard, show official Claude Desktop and Codex quota windows, build the verified 1.0.2_0031 real-time firmware, install it through Xiaomi OTA, diagnose LAN refreshes, or explain and control Flash wear.
---

# CUKTECH AP01 Screen Kit

Build a reusable AP01 project, choose the smallest applicable workflow, and
validate both the rendered asset and the device request path.

## Bootstrap a project

Use an existing AP01 project when present. Otherwise copy the bundled template:

```bash
python3 "<skill-root>/scripts/create_project.py" ./cuktech-ap01-screen \
  --venv
cd ./cuktech-ap01-screen
```

Do not copy firmware, cookies, tokens, signed URLs, device IDs, or generated
artifacts into a shareable project.

## Choose the workflow

1. **Replace artwork on an already-patched display**: read
   [references/custom-content.md](references/custom-content.md). Convert the
   asset, atomically replace the served GIF, and avoid OTA.
2. **Create or restyle a Claude/Codex quota panel**: read
   [references/quota-dashboard.md](references/quota-dashboard.md). Fetch the
   signed-in official accounts, edit `render_master()`, run tests, and serve
   the lightweight GIF.
3. **Install real-time loading for the first time**: read
   [references/realtime-firmware.md](references/realtime-firmware.md). Verify
   the exact firmware version before touching binary offsets.
4. **Fix connectivity, IP changes, or persistent service operation**: read
   [references/network-operations.md](references/network-operations.md).

## Preserve device invariants

- Emit exactly 320x240 GIF89a with at least two frames.
- Prefer two slow frames and less than 90 KB for smooth decoding.
- Keep rows `0..39` empty when retaining the stock clock/date overlay.
- Keep the Mac and AP01 on the same non-isolated LAN and reserve the Mac IP.
- Treat the firmware patch as specific to model `njcuk.enstor.ap01`, firmware
  `1.0.2_0031`; do not reuse its offsets on another build.
- Start the bridge before installing and require a logged AP01
  `GET /screen.gif` after reboot.
- Install the real-time firmware once. Perform later screen updates through
  `/tmp/.ap01q*.gif` RAM slots instead of OTA.
- Never pass an already real-time-patched image through
  `ap01_custom_ota.py`; that would overwrite the injected payload area.

## Validate before delivery

Run the available unit tests and inspect the 2x preview. For arbitrary content,
validate dimensions, GIF version, frame count, trailer, and byte size. For a
firmware build, retain the patcher's manifest, CRC, MD5, payload readback,
hook-target checks, and zero-relocation result.

Confirm the bridge health and device request:

```bash
curl --noproxy '*' http://127.0.0.1:8765/health
```

Report separately:

- design-master size;
- device-GIF dimensions, frames, and bytes;
- refresh interval and latest AP01 request time;
- whether OTA was required;
- that recurring updates use RAM rather than Flash.

## Bundled resources

- `scripts/create_project.py`: create a clean working project from the template.
- `assets/project-template/`: renderer, bridges, firmware builder, exact-image
  installer, payload source, icons, tests, and dependency list.
- `references/`: load only the workflow relevant to the user's request.
