# First-time real-time firmware workflow

The verified binary offsets in this kit apply only to CUKTECH AP01 firmware
`1.0.2_0031`, model `njcuk.enstor.ap01`. Refuse to reuse these offsets on a
different version; port the reverse-engineered hooks first.

## Prerequisites

- Log into Mi Home, Claude Desktop, Codex, and the AP01's Xiaomi account on the
  Mac that will run the bridge.
- Put the Mac and AP01 on the same non-isolated LAN.
- Reserve the Mac's IPv4 address in DHCP before building the firmware URL.
- Install Python dependencies plus `riscv64-elf-gcc` and
  `riscv64-elf-binutils`.

## Build

Download the matching stock firmware:

```bash
.venv/bin/python mi_cloud.py firmware
.venv/bin/python mi_cloud.py download
```

Build a shortened compatibility image containing the fallback GIF:

```bash
.venv/bin/python ap01_custom_ota.py artifacts/screen.gif \
  --firmware artifacts/ap01-1.0.2_0031.bin \
  --output artifacts/ap01-1.0.2_0031-screen-compat.bin
```

Inject the RAM-backed HTTP loader using the Mac's actual LAN IP:

```bash
.venv/bin/python ap01_realtime_patch.py \
  --input artifacts/ap01-1.0.2_0031-screen-compat.bin \
  --output artifacts/ap01-1.0.2_0031-screen-realtime.bin \
  --build-dir artifacts/realtime-build \
  --url http://MAC_LAN_IP:8765/screen.gif \
  --refresh-seconds 300
```

Never pass an already patched real-time image back through
`ap01_custom_ota.py`; replacing the pet slot would erase the injected payload.

## Validate and install

Start the bridge before installation. Validate transport first, then install
the exact prebuilt image without rebuilding it:

```bash
.venv/bin/python ap01_install_firmware.py \
  artifacts/ap01-1.0.2_0031-screen-realtime.bin --download-only
.venv/bin/python ap01_install_firmware.py \
  artifacts/ap01-1.0.2_0031-screen-realtime.bin --install
```

AP01 has no FDS configuration of its own. Its DID/model returns `code=-6`
from `/home/genpresignedurl`. The default uploader therefore needs a real
FDS-enabled `lumi.gateway.*` or `xiaomi.gateway.*` identity from the signed-in
account. That gateway identity is used only for upload; `deliver()` still
targets the AP01 DID.

If the AP01 account has no such gateway, separate upload from delivery. On a
trusted account containing an FDS-enabled gateway, upload the exact BIN:

```bash
.venv/bin/python ap01_install_firmware.py artifacts/screen-realtime.bin \
  --upload-only --url-output /tmp/ap01-ota-url.txt
```

Transfer the short-lived URL file to the AP01 owner and immediately validate
without installing:

```bash
.venv/bin/python ap01_install_firmware.py artifacts/screen-realtime.bin \
  --download-only --ota-url-file /path/to/ap01-ota-url.txt --timeout 360
```

Both commands must refer to byte-identical firmware. There is no AP01 bucket
or hidden AP01 FDS model to enter manually. Explicit `--fds-did` and
`--fds-model` options select a real gateway when automatic discovery is
ambiguous; they cannot grant FDS capability to AP01.

Require OTA state progression through downloaded/installed, a rebooted uptime,
and an AP01 request for `/screen.gif`. The normal charging UI is unchanged;
select the virtual-pet page to view custom content.

## Runtime storage

The loader writes only these RAM-backed tmpfs files:

```text
/tmp/.ap01q0.gif
/tmp/.ap01q1.gif
/tmp/.ap01q2.gif
/tmp/.ap01q.meta
/tmp/.ap01q.ack
```

OTA writes Flash once. Later content and quota refreshes do not write the
firmware/resource partitions.
