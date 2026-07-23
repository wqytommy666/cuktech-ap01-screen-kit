# Network and long-running operation

## Confirm the correct LAN

Compare the Bridge-computer interface and AP01 cloud-reported network before embedding a
URL:

```bash
ipconfig getifaddr en0
.venv/bin/python mi_cloud.py device
```

Windows PowerShell can obtain the routed address with:

```powershell
Get-NetIPConfiguration | Where-Object IPv4DefaultGateway
$env:AP01_LAN_IP = "192.168.1.100"  # optional explicit adapter selection
```

Do not trust matching `192.168.x.x` prefixes alone. Confirm the same SSID and
test AP01-to-computer connectivity; guest/IoT isolation can block local HTTP even
when both addresses look compatible.

Run the non-destructive probe when needed:

```bash
.venv/bin/python ap01_local_probe.py --outbound-test \
  --local-ip COMPUTER_LAN_IP --timeout 3
```

## Keep the address stable

Reserve the Bridge computer's address in the router's DHCP configuration
**before building or installing the loader**. The firmware URL contains a
literal IPv4 address and cannot discover the computer after DHCP changes.

Use the router's client list as the source of truth for the routed interface's
current IP and MAC. On macOS, Private Wi-Fi Address must remain fixed rather
than rotating; if its mode changes, reconnect and recreate the reservation for
the new router-visible MAC. Reconnect or reboot once and verify the address
before embedding it.

If the host address changes later:

1. inspect the router client/DHCP tables and the loader manifest URL;
2. restore the embedded old address when it is free — this requires no OTA;
3. never add an old address merely because ping is silent; another client or
   stale DHCP lease may own it;
4. when the old address is occupied or unrecoverable, reserve a new address,
   validate `/health` and `/screen.gif` through it, then rebuild from the
   reviewed stock/compat input and reinstall once with explicit confirmation.

When the router cannot provide a reservation, tell the user before install
that a future address change may require the recovery or one-time reinstall
above. Do not repeatedly install while the address is still unstable. See
`docs/STABLE_IP_GUIDE.md` or `docs/STABLE_IP_GUIDE.zh-CN.md` in the repository.

## Keep the bridge alive

Run the bridge in a persistent terminal, macOS `launchd`, Windows Task
Scheduler, or another process
supervisor. Verify `/health` and watch for AP01 `/screen.gif` requests. If the
bridge stops, AP01 retains its last decoded RAM image until reboot and retries
every 30 seconds; after reboot it displays the embedded fallback until the
bridge returns.
