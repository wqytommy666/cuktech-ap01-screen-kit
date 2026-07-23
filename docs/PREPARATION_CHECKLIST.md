# CUKTECH Screen Controller preparation and connectivity checklist

Before installing, separate the three workflows: normal artwork updates,
internet-backed quota refreshes, and the one-time loader installation for a
stock AP01.

## 1. Identify the display state

| Display state | Correct action |
| --- | --- |
| It has shown computer-supplied artwork, GIFs, or a quota dashboard | The real-time loader exists. Install the app and **do not OTA again** |
| Completely stock; it has never shown computer-supplied content | Verify the exact model and firmware, then use the coding-agent loader workflow once |
| Unknown | Run read-only diagnostics and look for `GET /screen.gif 200`; do not guess or flash it |

## 2. Hardware

- A CUKTECH 10 charging station and its detachable AP01 display;
- stable AP01 power, especially during a first loader installation;
- model `njcuk.enstor.ap01` on firmware `1.0.2_0031` for the published loader;
- either Apple Silicon macOS 14+ or Windows 10/11 x64. Both platforms have a
  desktop GUI and also support the coding-agent/Python workflow. Intel Mac and
  native Windows-on-ARM packages are not currently provided;
- no USB data cable is required. Normal content delivery uses Wi-Fi/LAN rather
  than USB or the charging-base contacts.

## 3. LAN preparation

Pair the AP01/charging station in Mi Home and make sure it is online. Put the
Bridge computer and AP01 on the same reachable LAN, not a guest network.
Disable AP/client isolation, allow incoming connections when macOS asks (or
allow Python on Windows Private networks), and allow TCP port `8765` through
VPN/firewall software. Ethernet is fine if it can
reach the AP01 across the same LAN/VLAN.

Before the first loader installation, reserve the Bridge computer's LAN
address with DHCP. Use the IP/MAC shown by the router and never take an address
already assigned to another device. The AP01 must be able to request:

```text
http://<COMPUTER_LAN_IP>:8765/screen.gif
```

The end-to-end success signal is a logged request such as:

```text
AP01_IP "GET /screen.gif HTTP/1.0" 200
```

### Why this reservation is a loader precondition

The loader stores the complete `http://COMPUTER_IP:8765/screen.gif` URL and
does not discover a host after DHCP changes. On macOS, keep Private Wi-Fi
Address fixed rather than rotating. Reconnect or restart once and prove that
the address remains unchanged before installing.

If reservation is unavailable, installation can continue only with a clear
recovery plan: restore the embedded old IP first without writing Flash; when
that is impossible, stabilize a new IP and rebuild, validate, and reinstall
the loader once. See the [stable-IP guide](STABLE_IP_GUIDE.md).

## 4. Internet requirements

| Workflow | Bridge computer internet | AP01 internet | Local LAN |
| --- | --- | --- | --- |
| Local artwork on an already-patched display | Only for initial download | No | Required |
| Claude/Codex live quotas (macOS / Windows) | Required for quota refreshes | No, but it must reach the Bridge | Required |
| First loader installation on a stock display | Required | Required and online in Mi Home | Required |

If the WAN fails but the LAN remains available, local artwork can still work.
Quota mode retains its last successful values until internet access returns.

## 5. Accounts

For quota mode, install and sign in to the official Claude Desktop and
Codex/ChatGPT app, or a signed-in Codex CLI. Approve Claude Safe Storage access
when macOS asks. Windows uses current-user DPAPI to read Claude Desktop's local
session in memory. Never paste cookies, passwords, or Keychain data into a chat.

For a first loader installation, have the target AP01 owner's Mi Home account
available and use the same device region. The gateway-free action uses the
restricted shared FDS relay, so the AP01 owner does not need to buy a gateway
or send Xiaomi credentials to the relay. Keep Xiaomi
credentials, DIDs, signed URLs, firmware binaries, and generated artifacts out
of GitHub.

## 6. Continuous operation

Both desktop installers create a per-user login Bridge. Keep the Bridge computer awake and the user
logged in for live updates. Quota mode changes to a disconnected page after
about seven offline minutes, while custom artwork remains unchanged. The
Bridge cannot refresh while the computer sleeps or is offline. Its normal poll
interval is about five minutes, so a pushed image may not appear immediately.

## 7. Final checklist

- [ ] Chosen platform: Apple Silicon macOS app, or Windows 10/11 x64 app
- [ ] AP01 on stable power and online in Mi Home
- [ ] Same non-guest, non-isolated LAN
- [ ] Local TCP 8765 allowed by macOS/Windows/VPN/firewall
- [ ] Bridge-computer DHCP reservation configured and verified after reconnect
- [ ] macOS Private Wi-Fi Address is fixed, or the reservation was recreated for the router-visible MAC
- [ ] If reservation is impossible, the user understands that an unrecoverable address change requires one loader reinstall
- [ ] Official Claude/Codex clients signed in for quota mode
- [ ] Stock loader work verified as `njcuk.enstor.ap01` / `1.0.2_0031`
- [ ] User understands daily updates use `/tmp` RAM and do not reinstall firmware

Continue with the [beginner guide](BEGINNER_GUIDE.md) after these checks pass.
