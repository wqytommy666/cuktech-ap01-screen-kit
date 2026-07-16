# Network and long-running operation

## Confirm the correct LAN

Compare the Mac interface and AP01 cloud-reported network before embedding a
URL:

```bash
ipconfig getifaddr en0
.venv/bin/python mi_cloud.py device
```

Do not trust matching `192.168.x.x` prefixes alone. Confirm the same SSID and
test AP01-to-Mac connectivity; guest/IoT isolation can block local HTTP even
when both addresses look compatible.

Run the non-destructive probe when needed:

```bash
.venv/bin/python ap01_local_probe.py --outbound-test \
  --local-ip MAC_LAN_IP --timeout 3
```

## Keep the address stable

Reserve the Mac address in the router's DHCP configuration. The firmware URL
contains a literal IPv4 address. If it changes, either restore the reservation
or rebuild/reinstall the firmware once with the new address.

## Keep the bridge alive

Run the bridge in a persistent terminal, `launchd`, or another process
supervisor. Verify `/health` and watch for AP01 `/screen.gif` requests. If the
bridge stops, AP01 retains its last decoded RAM image until reboot and retries
every 30 seconds; after reboot it displays the embedded fallback until the
bridge returns.
