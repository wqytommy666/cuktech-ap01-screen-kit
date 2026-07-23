# CUKTECH Screen Controller beginner guide

This guide is for people who do not normally use Terminal or write code.

> Native desktop apps are available for macOS and Windows. Windows screenshots
> and platform-specific troubleshooting are in the [Windows guide](WINDOWS_GUIDE.md).

## Before you begin

Prepare an Apple Silicon Mac running macOS 14+ or a Windows 10/11 x64 PC. Keep
the AP01 powered, pair it in Mi Home, and put the computer and AP01 on the same reachable, non-guest
LAN. Allow local incoming connections to TCP port `8765`. For the quota
dashboard, install and sign in to Claude Desktop and the official
Codex/ChatGPT app. See the full [preparation checklist](PREPARATION_CHECKLIST.md).

The project transfers screen content over Wi-Fi/LAN, not USB or the base
contacts. Local artwork does not need internet after the loader is installed.
Quota refreshes need internet on the computer. A first loader installation on a
stock screen needs both the computer and AP01 online, with the AP01 visible in Mi
Home and kept on stable power.

Before a first loader installation, reserve the Bridge computer's current IP
in the router and verify it after reconnecting. AP01 stores a literal IP and
does not automatically follow DHCP changes. On macOS keep Private Wi-Fi
Address fixed rather than rotating. Read the
[Bridge IP reservation and recovery guide](STABLE_IP_GUIDE.md) before install.

If the AP01 has already shown a custom image or quota dashboard, its real-time
loader is installed and normal updates only use RAM. A completely stock AP01
needs the supported loader installed once. Open **First deployment / OTA** and
choose **Gateway-free: get deployment package**. No Xiaomi gateway or manual
firmware file is required. The app checks `njcuk.enstor.ap01 / 1.0.2_0031`,
performs download-only verification, and asks again immediately before install.

## Install the app

1. Download the ZIP for your operating system from
   [GitHub Releases](https://github.com/wqytommy666/cuktech-screen-controller/releases/latest).
2. On macOS, unzip it and open `Install CUKTECH Screen Controller.command`.
3. On Windows, use **Extract All**, then open `Install CUKTECH Screen Controller.cmd`.
4. Allow local/private-network access when the operating system asks.
5. Follow the in-app **新手引导 / Getting started** readiness checks.

For a stock AP01, open **First deployment / OTA**, choose the gateway-free
package action only after the Bridge IP is reserved, run download-only
verification, then use the separately confirmed install action. Users whose
AP01 already shows custom content must skip this step and must not reinstall
the loader merely to change artwork.

Choose **显示 Claude / Codex 额度** for quotas, or choose a fit mode and click
**选择图片并推送** for an image or animated GIF. The Windows Release is
self-contained and does not require a separate Python installation.

## Give the repository to a coding agent

Give Claude Code, Codex, OpenCode, WorkBuddy, or another terminal-capable agent
this URL:

```text
https://github.com/wqytommy666/cuktech-screen-controller
```

Use this prompt:

```text
Read AGENTS.md, README.md, and skills/cuktech-ap01-screen-kit/SKILL.md first.
I am not a programmer, so ask for only one manual action at a time. Detect
whether this computer runs macOS or Windows and run the matching read-only
diagnostic before making changes. On Windows, read docs/WINDOWS_GUIDE.md and
do not run scripts under macos/. Configure the app/Bridge, verify
/health, validate the 320x240 GIF89a, and show a logged AP01 GET /screen.gif
200. If the real-time loader is already installed, do not use OTA. If it is
missing, verify the exact supported AP01 model and firmware and ask me again
immediately before the one-time installation. Before building, identify the
Bridge host's IP/MAC in the router, create a DHCP reservation, reconnect, and
verify that it remains unchanged. If reservation is unavailable, explain that
a later DHCP change requires restoring the embedded old IP or one rebuild and
reinstall for a stabilized new IP. Daily updates must use /tmp RAM.
```

## If something stops updating

Open the in-app beginner guide and rerun its checks. On either platform, ask
the agent to detect the OS and repair the Bridge without OTA. Windows uses
`scripts/diagnose-windows.ps1`; macOS uses:

```text
Run ./macos/diagnose.sh and repair the Bridge without performing OTA.
```

The Bridge computer must remain logged in and connected to the same reachable
LAN. In quota mode, AP01 changes to a disconnected page after about seven
offline minutes; user-selected custom artwork remains unchanged.

If `/health` works locally but no AP01 `GET /screen.gif` appears, compare the
computer's current IP with the address embedded in the loader. Restore the old
IP in the router first without reflashing. Only when the old address cannot be
restored should you reserve a new one and perform one validated loader
reinstall. Never force an old address that the router shows as occupied.
