# CUKTECH Screen Controller — Agent operating guide

This repository controls a CUKTECH AP01 detachable display.  Treat the two
operations below as different workflows:

- **Daily screen refresh:** serve a 320×240 GIF over the LAN.  The AP01 writes
  it to rotating `/tmp/.ap01q*.gif` RAM slots.  This is the normal path.
- **One-time real-time loader installation:** modify and install firmware for
  the exact supported model/build.  This writes Flash and requires explicit
  user confirmation.

## Start here on every new computer

1. Read `README.zh-CN.md` (or `README.md`) and
   `skills/cuktech-ap01-screen-kit/SKILL.md`.
2. Detect the host operating system and run only read-only checks first:

   ```bash
   # macOS
   ./macos/diagnose.sh

   # Windows PowerShell
   powershell -ExecutionPolicy Bypass -File scripts/diagnose-windows.ps1
   ```

   A non-zero result before installation simply means prerequisites are still
   missing; read the printed checklist and continue with the applicable setup.

3. Confirm all of the following with the user:
   - Apple Silicon macOS 14+ for the macOS package, or Windows 10/11 x64 for
     the Windows package; the Python/coding-agent toolkit supports both;
   - the AP01 is powered, paired in Mi Home, and shown online before any
     first-loader workflow;
   - the Bridge computer and AP01 are on the same LAN without client/AP isolation;
   - VPN/firewall rules permit LAN access to TCP 8765 and the Bridge computer's
     routed LAN address is reserved with DHCP before a loader build;
   - Claude Desktop and the official Codex/ChatGPT app are installed and
     signed in when automatic quota display is requested on either platform;
   - whether this AP01 already requests `GET /screen.gif` from the Bridge computer;
   - exact AP01 model and firmware before any loader work.

   Explain the network requirement precisely: already-patched local artwork
   needs only a working LAN; automatic quota refreshes need internet on the
   host computer; a first-loader installation needs the AP01 and installation
   environment online. USB and the
   charging-base contacts are not the screen-content transport used here.
   Explain that the loader embeds a literal IPv4 URL. Record the routed
   interface, router-visible MAC, current IP, and reservation status before a
   first install. On macOS keep Private Wi-Fi Address fixed, not rotating. If
   reservation is unavailable, explicitly explain that a later address change
   requires restoring the old IP or one rebuilt/reinstalled loader for a
   stabilized new IP.
4. For a source/agent installation, run the platform-appropriate setup:

   ```bash
   ./scripts/setup-macos.sh

   # Windows PowerShell
   powershell -ExecutionPolicy Bypass -File scripts/setup-windows.ps1 -App
   ```

5. Verify both endpoints and the device request:

   ```bash
   # macOS
   curl --noproxy '*' http://127.0.0.1:8765/health
   curl --noproxy '*' -I http://127.0.0.1:8765/screen.gif
   ./macos/diagnose.sh

   # Windows PowerShell
   Invoke-RestMethod http://127.0.0.1:8765/health
   Invoke-WebRequest -Method Head http://127.0.0.1:8765/screen.gif
   .\scripts\diagnose-windows.ps1
   ```

## Choose the smallest workflow

- Already sees AP01 `GET /screen.gif`: do **not** perform OTA.  Configure quota
  mode or convert custom artwork and restart the Bridge.
- No real-time loader: verify exact model `njcuk.enstor.ap01` and firmware
  `1.0.2_0031`, then follow
  `skills/cuktech-ap01-screen-kit/references/realtime-firmware.md`.
- Custom image: follow
  `skills/cuktech-ap01-screen-kit/references/custom-content.md`.
- Claude/Codex quota panel: follow
  `skills/cuktech-ap01-screen-kit/references/quota-dashboard.md`.
- Network/startup issue: follow
  `skills/cuktech-ap01-screen-kit/references/network-operations.md`.

## Non-negotiable checks

- Never guess firmware offsets or reuse the patch on another build.
- Never OTA an already real-time-patched image through `ap01_custom_ota.py`.
- Never run OTA merely to update artwork or quota values.
- Never force an old IP onto the Bridge until the router client/DHCP tables
  prove it is free; a failed ping is not sufficient evidence.
- When `GET /screen.gif` disappears after a host-address change, restore the
  embedded old IP first without OTA. Rebuild/reinstall only when the old
  address cannot be recovered, and reserve the new address before building.
- Never commit cookies, Xiaomi credentials, device IDs, signed OTA URLs,
  firmware binaries, or generated `artifacts/`.
- Require the user's explicit confirmation immediately before a one-time
  firmware installation.
- A successful handoff includes `/health`, a valid GIF89a, and a logged AP01
  `GET /screen.gif 200` request.
