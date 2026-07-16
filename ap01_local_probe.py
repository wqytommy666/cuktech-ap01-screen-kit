#!/usr/bin/env python3
"""Non-destructive LAN reachability/protocol probe for the CUKTECH AP01.

The default probe sends only a standard 32-byte MiIO discovery packet and TCP
SYN/connect attempts.  ``--outbound-test`` additionally asks the already-bound
AP01, through Xiaomi cloud RPC, to send one 64-byte UDP iperf packet to this Mac.
No device property, Wi-Fi credential, firmware, or flash partition is changed.
"""

from __future__ import annotations

import argparse
import errno
import ipaddress
import json
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from mi_cloud import MiCloud, MODEL

MIIO_PORT = 54321
MIIO_HELLO = bytes.fromhex(
    "21310020" + "ffffffff" * 3 + "00" * 16
)
DEFAULT_TCP_PORTS = (22, 23, 53, 80, 443, 1883, 5353, 6666, 8000, 8080, 8883, 8888)


def miio_header(packet: bytes) -> dict[str, Any] | None:
    if len(packet) < 32 or packet[:2] != b"\x21\x31":
        return None
    magic, length, unknown, did, timestamp = struct.unpack(">HHIII", packet[:16])
    return {
        "magic": f"0x{magic:04x}",
        "length": length,
        "unknown": unknown,
        "did": did,
        "timestamp": timestamp,
    }


def direct_hello(ip: str, timeout: float) -> dict[str, Any]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    started = time.monotonic()
    try:
        sock.sendto(MIIO_HELLO, (ip, MIIO_PORT))
        data, source = sock.recvfrom(2048)
        return {
            "status": "reply",
            "source": f"{source[0]}:{source[1]}",
            "rtt_ms": round((time.monotonic() - started) * 1000, 1),
            "bytes": len(data),
            "header": miio_header(data),
        }
    except socket.timeout:
        return {"status": "timeout"}
    except OSError as exc:
        return {
            "status": "os_error",
            "errno": exc.errno,
            "error": exc.strerror or str(exc),
        }
    finally:
        sock.close()


def broadcast_hello(broadcast: str, timeout: float) -> list[dict[str, Any]]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.15)
    replies: list[dict[str, Any]] = []
    try:
        # Three hellos matches Xiaomi's own discovery client and avoids losing the
        # one small UDP broadcast while the display is busy drawing.
        for _ in range(3):
            sock.sendto(MIIO_HELLO, (broadcast, MIIO_PORT))
            time.sleep(0.03)
        deadline = time.monotonic() + timeout
        seen: set[tuple[str, int]] = set()
        while time.monotonic() < deadline:
            try:
                data, source = sock.recvfrom(2048)
            except socket.timeout:
                continue
            if source in seen:
                continue
            seen.add(source)
            replies.append(
                {
                    "source": f"{source[0]}:{source[1]}",
                    "bytes": len(data),
                    "header": miio_header(data),
                }
            )
    except OSError as exc:
        replies.append(
            {"broadcast_error": exc.strerror or str(exc), "errno": exc.errno}
        )
    finally:
        sock.close()
    return replies


def tcp_probe(ip: str, ports: tuple[int, ...], timeout: float) -> list[dict[str, Any]]:
    results = []
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        started = time.monotonic()
        try:
            code = sock.connect_ex((ip, port))
            item: dict[str, Any] = {
                "port": port,
                "status": "open" if code == 0 else errno.errorcode.get(code, str(code)),
                "rtt_ms": round((time.monotonic() - started) * 1000, 1),
            }
        except OSError as exc:
            item = {
                "port": port,
                "status": errno.errorcode.get(exc.errno or -1, "OS_ERROR"),
                "errno": exc.errno,
            }
        finally:
            sock.close()
        results.append(item)
    return results


def arp_entry(ip: str) -> str:
    try:
        run = subprocess.run(
            ["arp", "-n", ip], capture_output=True, text=True, timeout=2, check=False
        )
        return (run.stdout or run.stderr).strip()
    except Exception as exc:
        return f"arp unavailable: {exc}"


def infer_local_ip(interface: str, target_ip: str) -> str:
    try:
        run = subprocess.run(
            ["ipconfig", "getifaddr", interface],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        candidate = run.stdout.strip()
        if candidate:
            return candidate
    except Exception:
        pass
    # Portable fallback: no packet is sent by UDP connect().
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((target_ip, 9))
        return sock.getsockname()[0]
    finally:
        sock.close()


def controlled_outbound_test(
    cloud: MiCloud, did: str, local_ip: str, port: int, timeout: float
) -> dict[str, Any]:
    capture: dict[str, Any] = {"packets": 0, "bytes": 0, "sources": []}
    sources: set[tuple[str, int]] = set()
    ready = threading.Event()

    def receiver() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", port))
        sock.settimeout(0.15)
        ready.set()
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                try:
                    payload, source = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                capture["packets"] += 1
                capture["bytes"] += len(payload)
                sources.add(source)
        finally:
            sock.close()

    thread = threading.Thread(target=receiver, daemon=True)
    thread.start()
    ready.wait(1)
    params = {
        "mode": "udp",
        "ip": local_ip,
        "port": port,
        "packet_size": 64,
        "time": 1,
        "interval": 1,
    }
    rpc = cloud.rpc(did, "miIO.iperf_client", params)
    thread.join()
    capture["sources"] = [f"{host}:{source_port}" for host, source_port in sorted(sources)]
    return {
        "rpc": {
            key: rpc.get(key)
            for key in ("code", "message", "result", "error", "exe_time")
            if key in rpc
        },
        "capture": capture,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", help="AP01 LAN IPv4; without it the Xiaomi account is queried")
    parser.add_argument("--did", help="optional expected Xiaomi DID for matching broadcast replies")
    parser.add_argument("--mac", help="optional AP01 MAC for the static-ARP hint")
    parser.add_argument(
        "--show-other-devices", action="store_true",
        help="include other MiIO broadcast responders in JSON",
    )
    parser.add_argument("--broadcast", help="subnet broadcast address; default target /24 .255")
    parser.add_argument("--interface", default="en0", help="Mac LAN interface (default: en0)")
    parser.add_argument("--local-ip", help="Mac LAN IPv4 for --outbound-test")
    parser.add_argument("--timeout", type=float, default=1.5)
    parser.add_argument(
        "--tcp-ports",
        default=",".join(map(str, DEFAULT_TCP_PORTS)),
        help="comma-separated, conservative TCP port list",
    )
    parser.add_argument(
        "--outbound-test",
        action="store_true",
        help="cloud-trigger one 64-byte AP01-to-Mac UDP packet",
    )
    parser.add_argument("--listen-port", type=int, default=45888)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    cloud: MiCloud | None = None
    did = args.did
    ip = args.ip
    model = MODEL
    mac = args.mac
    if not ip or args.outbound_test:
        cloud = MiCloud()
        device = cloud.ap01()
        ip = ip or str(device["localip"])
        did = did or str(device["did"])
        model = str(device.get("model") or MODEL)
        mac = mac or device.get("mac")
    assert ip

    target = ipaddress.ip_address(ip)
    if target.version != 4:
        raise SystemExit("AP01 probe currently expects IPv4")
    broadcast = args.broadcast or str(ipaddress.ip_network(f"{ip}/24", strict=False).broadcast_address)
    ports = tuple(int(part) for part in args.tcp_ports.split(",") if part.strip())

    direct_before = direct_hello(ip, args.timeout)
    all_broadcast_replies = broadcast_hello(broadcast, args.timeout)
    target_broadcast = [
        item
        for item in all_broadcast_replies
        if item.get("source", "").split(":", 1)[0] == ip
        or (did and str((item.get("header") or {}).get("did")) == did)
    ]
    broadcast_report: dict[str, Any] = {
        "address": broadcast,
        "target_replies": target_broadcast,
        "other_reply_count": max(0, len(all_broadcast_replies) - len(target_broadcast)),
    }
    if args.show_other_devices:
        broadcast_report["all_replies"] = all_broadcast_replies
    report: dict[str, Any] = {
        "target": {"model": model, "ip": ip, "did": did, "mac": mac},
        "arp": arp_entry(ip),
        "miio_direct_54321": direct_before,
        "miio_broadcast": broadcast_report,
        "miio_direct_after_broadcast": direct_hello(ip, args.timeout),
        "tcp": tcp_probe(ip, ports, min(args.timeout, 0.6)),
    }

    if args.outbound_test:
        assert cloud is not None and did
        local_ip = args.local_ip or infer_local_ip(args.interface, ip)
        report["outbound_test"] = {
            "mac_ip": local_ip,
            **controlled_outbound_test(
                cloud, did, local_ip, args.listen_port, max(args.timeout + 2.0, 4.0)
            ),
        }

    direct = report["miio_direct_after_broadcast"]["status"]
    if direct == "reply":
        conclusion = "AP01 的本地 MiIO/UDP 54321 单播可达，可以继续测试离线本地 RPC。"
    elif target_broadcast:
        conclusion = (
            "AP01 的 MiIO/UDP 54321 监听器确实在运行并响应广播，但 Mac→AP01 的单播被 "
            "ARP/跨频段/无线客户端隔离阻断。先关闭路由器的 AP/访客/IoT 隔离，或把 Mac "
            "与 AP01 放到同一 2.4 GHz BSSID；也可临时设置静态 ARP 后复测。"
        )
    elif direct == "os_error":
        conclusion = "Mac 到 AP01 的新建入站路径在二层/路由层不可达，或设备拒绝 ARP；尚未收到本地 MiIO 响应。"
    else:
        conclusion = "AP01 未响应本地 MiIO/UDP 54321；可能未启用本地监听，也可能被无线隔离策略过滤。"
    if args.outbound_test:
        packets = report["outbound_test"]["capture"]["packets"]
        conclusion += (
            f" 受控出站测试收到 {packets} 个包，证明 AP01→Mac 的局域网出站路径可用。"
            if packets
            else " 受控出站测试也未收到 AP01 数据。"
        )
    report["conclusion"] = conclusion

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
