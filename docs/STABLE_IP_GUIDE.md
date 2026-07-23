# Bridge IP reservation and address-change recovery

The AP01 real-time loader stores a complete URL with a **literal IPv4
address**, for example:

```text
http://192.168.31.100:8765/screen.gif
```

It does not discover the computer automatically, and the embedded URL does not
change when DHCP gives the computer another address. **Reserve the Bridge
computer's address before the first loader installation.** This is a LAN DHCP
reservation, not port forwarding and not a public static IP.

## Recommended setup: reserve the current address in the router

1. Start CUKTECH Screen Controller and its Bridge.
2. Find the computer in the router's connected-device or DHCP-client list. Use
   the **IP and MAC shown by the router**.
3. Open the router's LAN/DHCP page and choose **DHCP reservation**, **static
   lease**, or **static DHCP assignment**.
4. Bind the computer's current IP to its current MAC. Never take an address
   that is already assigned to another device.
5. Reconnect the network or restart the computer and verify that the address
   is unchanged.
6. Only then embed that address in the AP01 loader and install it.

Useful read-only checks:

```bash
# macOS: identify the routed interface before reading its address
route -n get default | grep interface
ipconfig getifaddr en0
ifconfig en0 | awk '/ether/{print $2}'
```

```powershell
# Windows PowerShell
Get-NetIPConfiguration | Where-Object IPv4DefaultGateway |
  Select-Object InterfaceAlias,@{N='IPv4';E={$_.IPv4Address.IPAddress}}
Get-NetAdapter | Where-Object Status -eq Up |
  Select-Object Name,MacAddress
```

A computer may have Wi-Fi, Ethernet, dock, and VPN interfaces. Reserve the LAN
interface that the AP01 can actually reach and that the Bridge uses, not simply
the first address in a list.

## macOS Private Wi-Fi Address

macOS may present a private MAC to the router. The reservation must use the
MAC currently shown for this network, which may differ from the hardware MAC.

- In **System Settings → Wi-Fi → current network → Details**, keep Private
  Wi-Fi Address set to **Fixed**. On older macOS versions with only an on/off
  choice, choose one mode and do not change it later.
- Do not use a periodically rotating mode for the Bridge network.
- After changing the private-address mode, reconnect Wi-Fi, recreate the DHCP
  reservation for the new MAC, and only then build the loader.

## Required validation before installation

If the planned loader address is `192.168.31.100`, verify at least:

```bash
curl --noproxy '*' http://192.168.31.100:8765/health
curl --noproxy '*' -I http://192.168.31.100:8765/screen.gif
```

`/health` must succeed, and `screen.gif` must return HTTP 200 with
`Content-Type: image/gif`. After installation and reboot, the Bridge log must
also contain an AP01 request such as:

```text
GET /screen.gif 200
```

## If the computer's IP changes later

A common symptom is a healthy local `/health` endpoint but no AP01
`GET /screen.gif` request. The display keeps an old image, a fallback, or a
disconnected page. Recover in this order:

| Recovery | AP01 Flash write? | Use when |
| --- | --- | --- |
| Restore the computer to the loader's original IP in the router | **No** | Preferred when the old address is free |
| Repair Bridge startup, firewall, or LAN isolation | **No** | The address is unchanged but the service is unreachable |
| Reserve a new IP, rebuild, and reinstall the loader | **One write** | The old address is occupied or cannot be restored |

Do not force the old address onto the computer until the router's client and
DHCP tables prove that it is free. A failed ping does not prove an address is
unused; duplicate IPs can break LAN access for the whole computer.

When a new address is unavoidable:

1. reserve the new address first;
2. verify `/health` and `/screen.gif` through that address;
3. rebuild from a reviewed stock/compatibility input image; never pass an
   already real-time-patched image through `ap01_custom_ota.py`;
4. recheck model `njcuk.enstor.ap01` and firmware `1.0.2_0031`;
5. obtain explicit user confirmation immediately before the OTA Flash write;
6. reboot and verify a new `GET /screen.gif 200` request.

Changing the embedded address requires one loader installation. Later images,
animated GIFs, and Claude/Codex quota updates still rotate through the
RAM-backed `/tmp/.ap01q*.gif` slots and do not rewrite Flash on every refresh.

## If DHCP reservation is unavailable

The loader can still be used, but plan for these limitations:

- a restart, router change, or forgetting/rejoining Wi-Fi may change the IP;
- restore the original embedded address first whenever possible;
- if restoration is impossible, reserve or otherwise stabilize a new address,
  then rebuild, validate, and reinstall the loader;
- never reinstall repeatedly while the address is still uncertain.

Solving address reservation before the first installation is the most stable
option and best avoids extra Flash writes.
