# Windows guide

CUKTECH Screen Controller now ships as a **Windows 10/11 x64 desktop app**.
It uses the same AP01 Bridge and screen format as the macOS edition: live
Claude/Codex quotas, artwork and animated GIFs, preview, login startup,
diagnostics, and first-time OTA ticket handoff.

![Windows main window](images/windows-controller-main.png)

## Install the app (recommended)

1. Open [GitHub Releases](https://github.com/wqytommy666/cuktech-screen-controller/releases/latest).
2. Download `CUKTECH-Screen-Controller-0.4.1-Windows-x64.zip`.
3. Use **Extract All**. Do not launch it from Explorer's ZIP preview.
4. Double-click `Install CUKTECH Screen Controller.cmd`.
5. Open the app from the Start menu.
6. When Windows Defender asks, allow **Private networks** only.

The app is installed under:

```text
%LOCALAPPDATA%\Programs\CUKTECH Screen Controller
```

Screens, mode and logs remain under:

```text
%LOCALAPPDATA%\CUKTECH Screen Controller
```

Re-running a newer installer updates the app without deleting this data.

## Supported features

| Feature | Windows 10/11 x64 |
| --- | --- |
| Native-feeling desktop controller | Yes |
| PNG/JPG/WebP/BMP/TIFF/animated GIF | Yes |
| `contain`, `cover`, `stretch` | Yes |
| Claude 5-hour/week/Fable 5 | Yes, from the signed-in Claude Desktop profile |
| Codex 5-hour/week | Yes, through the official local `app-server` |
| Five-minute refresh, preview and `/health` | Yes |
| Login background Bridge | Yes |
| BFNP preflight, FDS ticket and `download-only` | Yes |

The Claude collector reads the current user's Electron/Chromium profile and
uses Windows DPAPI in memory. Codex is queried through its official local
`app-server`. Session values are never written to the rendered image or quota
JSON.

## First run

Use **Getting started** in the top-right corner and confirm:

1. AP01 is powered, paired in Mi Home and online.
2. PC and AP01 share a non-guest, non-isolated LAN.
3. Claude Desktop and the official Codex/ChatGPT app are signed in for quota mode.
4. The Bridge status is online.
5. The log eventually contains `GET /screen.gif 200`.

![Windows onboarding](images/windows-controller-guide.png)

Normal content delivery uses **Wi-Fi/LAN**, not USB or the charging-base contacts.
Ethernet is fine when AP01 can reach the PC's private IPv4 address on TCP 8765.

## Custom artwork

Choose a fit mode, select an image, and press **Push**. The app produces a
validated 320×240 GIF89a with at least two frames, restarts the Bridge, and
serves it at the URL shown in the UI.

Local checks:

```text
http://127.0.0.1:8765/health
http://127.0.0.1:8765/screen.gif
```

If localhost works but AP01 never requests the image, use a Private Windows
network, allow `CUKTECHRuntime.exe` through Defender for Private networks,
disable VPN LAN blocking and router client isolation, and reserve the PC's
DHCP address.

## First-time OTA handoff

![Windows OTA handoff](images/windows-controller-ota.png)

Do **not** repeat OTA when AP01 can already show custom content. A stock unit
needs one loader matching model `njcuk.enstor.ap01` and firmware `1.0.2_0031`.
The Windows dialog can validate BFNP/SHA-256, import or create a temporary FDS
ticket, obtain a restricted gateway-free deployment package, run download-only
verification, and require a separate confirmation before the one-time install.

Windows has no Mi Home plist. Cloud operations therefore accept a local JSON
selected for the current process only; see `mi-credentials.example.json` in
the ZIP. Never commit or share that file. AP01 itself is not FDS-enabled, but
the gateway-free action can use the restricted shared relay without sending
that JSON, the AP01 DID or arbitrary firmware to the relay. See the
[relay operator and security guide](FDS_RELAY_OPERATOR.md).

## Run from source

With Python 3.9+ installed:

```powershell
git clone https://github.com/wqytommy666/cuktech-screen-controller.git
cd cuktech-screen-controller
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-windows.ps1 -App
```

Later launches:

```powershell
.\.venv\Scripts\pythonw.exe .\windows\AP01ScreenController.py
```

Read-only diagnostics:

```powershell
.\scripts\diagnose-windows.ps1
```

## Flash behavior

Only the first loader installation writes firmware Flash. Normal images and
quota updates rotate `/tmp/.ap01q0.gif` through `.ap01q2.gif`, which are
RAM-backed. A five-minute quota refresh does not repeatedly erase firmware or
resource partitions. In quota mode, the AP01 changes to a disconnected page
after about seven offline minutes; user-selected custom artwork stays static.

Requirements: Windows 10/11 x64, AP01 `njcuk.enstor.ap01`; the included loader
patch supports firmware `1.0.2_0031` only. A native Windows-on-ARM release is
not currently provided.
