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
