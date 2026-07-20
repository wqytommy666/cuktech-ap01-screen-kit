#!/usr/bin/env python3
"""Build and experimentally deliver a custom AP01 virtual-character screen.

The package keeps the vendor firmware layout and replaces only the five
compiled 320x240 virtual-character GIF resources. Upload goes through Xiaomi
FDS, because AP01 rejects plain HTTP OTA URLs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import struct
import time
import zlib
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
from PIL import Image

from mi_cloud import MODEL, MiCloud
from patch_asset import find_assets, image_info


HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
PET_INDICES = range(5)
RECOVERY_TAG = b"0x5245434f56455259544147"
OTA_CDN_HOST = "iot-ota-cdn.io.mi.com"


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recovery_crc(data: bytes | bytearray) -> int:
    """Return the CRC variant used by AP01's recovery-image validator.

    The firmware uses the normal reflected CRC-32 table, but starts at zero
    and does not apply the usual final xor.  Expressing that with zlib is much
    faster than a byte-at-a-time Python implementation.
    """

    return (zlib.crc32(data, 0xFFFFFFFF) ^ 0xFFFFFFFF) & 0xFFFFFFFF


def refresh_recovery_trailer(firmware: bytearray) -> int:
    """Update AP01's 40-byte recovery trailer after modifying the image.

    AP01 scans for the second RECOVERYTAG string, verifies a big-endian total
    file length at trailer+32, then compares a little-endian CRC32 stored in
    the final four bytes with the CRC of every preceding byte.  Keeping the
    vendor trailer CRC unchanged was why earlier images downloaded but were
    rejected before activation.
    """

    marker = firmware.rfind(RECOVERY_TAG)
    if marker < 0 or marker + 40 != len(firmware):
        raise RuntimeError("未找到 AP01 尾部的 40 字节 RECOVERYTAG")
    if firmware.find(RECOVERY_TAG) == marker:
        raise RuntimeError("固件中只找到一个 RECOVERYTAG，布局与 AP01 原版不符")

    struct.pack_into(">I", firmware, marker + 32, len(firmware))
    checksum = recovery_crc(firmware[:-4])
    struct.pack_into("<I", firmware, marker + 36, checksum)

    stored_length = struct.unpack_from(">I", firmware, marker + 32)[0]
    stored_crc = struct.unpack_from("<I", firmware, marker + 36)[0]
    if stored_length != len(firmware) or stored_crc != recovery_crc(firmware[:-4]):
        raise RuntimeError("RECOVERYTAG 长度/CRC 回读校验失败")
    return checksum


def build_firmware(source: Path, gif_path: Path, output: Path) -> None:
    firmware = bytearray(source.read_bytes())
    replacement = gif_path.read_bytes()
    kind, size, frames = image_info(replacement)
    if kind != "gif":
        raise RuntimeError(f"输入文件是 {kind}，不是 GIF")
    if size != (320, 240):
        raise RuntimeError(f"GIF 必须为 320x240，当前为 {size[0]}x{size[1]}")

    assets = find_assets(firmware, "gif")
    if len(assets) < 5:
        raise RuntimeError("固件中没有找到完整的虚拟形象资源表")
    for index in PET_INDICES:
        offset, capacity = assets[index]
        with Image.open(io.BytesIO(firmware[offset : offset + capacity])) as original:
            if original.size != (320, 240):
                raise RuntimeError(f"GIF[{index}] 不是预期的 320x240 资源")
        if len(replacement) > capacity:
            raise RuntimeError(
                f"GIF 为 {len(replacement)} 字节，超过最小槽位 {capacity} 字节；"
                "请减少帧数或颜色数"
            )
        firmware[offset : offset + capacity] = replacement + bytes(
            capacity - len(replacement)
        )
        struct.pack_into("<I", firmware, offset - 16, len(replacement))

    recovery_checksum = refresh_recovery_trailer(firmware)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(firmware)
    print(
        f"已替换 5 个虚拟形象槽位：{frames} 帧，{len(replacement)} 字节，"
        f"Recovery CRC 0x{recovery_checksum:08x}，固件 MD5 {md5_file(output)}"
    )


def choose_fds_device(
    cloud: MiCloud,
    *,
    did: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Choose the device identity used only to obtain an FDS upload URL.

    AP01 itself has no server-side FDS configuration, so its DID/model cannot
    be used here.  An explicit identity is useful when the uploader account
    has multiple gateway-class devices; it does not change the AP01 that later
    receives ``miIO.ota``.
    """

    if bool(did) != bool(model):
        raise ValueError("--fds-did 和 --fds-model 必须同时提供")
    if did and model:
        return {"did": str(did), "model": str(model)}

    # AP01 itself has no FDS upload configuration. Xiaomi gateways generally do.
    candidates = [
        item
        for item in cloud.devices()
        if str(item.get("model", "")).startswith(("lumi.gateway.", "xiaomi.gateway."))
    ]
    if not candidates:
        raise RuntimeError(
            "账号中未找到可用于 Xiaomi FDS 上传的网关。AP01 自身没有 FDS "
            "服务端配置，不能用 njcuk.enstor.ap01 的 DID/model 代替；请由含 "
            "FDS 网关的账号执行 --upload-only，或使用已签名的 --ota-url。"
        )
    return candidates[0]


def probe_ota_url(url: str) -> None:
    """Require the AP01-compatible CDN URL to return a BFNP image header."""

    probe = requests.get(
        url,
        headers={"Range": "bytes=0-3"},
        stream=True,
        timeout=30,
    )
    probe.raise_for_status()
    magic = next(probe.iter_content(4), b"")
    probe.close()
    if magic != b"BFNP":
        raise RuntimeError("OTA URL 回读文件头失败：不是 AP01 BFNP 镜像")


def upload_to_xiaomi(
    cloud: MiCloud,
    firmware: Path,
    *,
    fds_did: str | None = None,
    fds_model: str | None = None,
) -> str:
    gateway = choose_fds_device(cloud, did=fds_did, model=fds_model)
    request_payload = {
        "did": str(gateway["did"]),
        "model": str(gateway["model"]),
        "suffix": "bin",
    }
    prepared = cloud.request("home/genpresignedurl", request_payload)
    upload = (prepared.get("result") or {}).get("bin") or {}
    if not upload.get("ok") or not upload.get("url") or not upload.get("obj_name"):
        raise RuntimeError(
            "Xiaomi FDS 预签名失败："
            f"code={prepared.get('code')} "
            f"message={prepared.get('message', 'unknown')}；"
            "传入的 DID/model 必须属于当前账号中真正具备 FDS 配置的网关，"
            "不能使用 AP01 DID/model，也不存在可手工填写的 AP01 bucket。"
        )

    print("正在上传到 Xiaomi FDS…")
    # Do not add Content-Type: it is not part of Xiaomi's pre-signed PUT signature.
    with firmware.open("rb") as stream:
        response = requests.put(upload["url"], data=stream, timeout=180)
    response.raise_for_status()

    fetched = cloud.request("home/getfileurl", {"obj_name": upload["obj_name"]})
    result = fetched.get("result") or {}
    if not result.get("ok") or not result.get("url"):
        raise RuntimeError(f"Xiaomi FDS 下载签名失败：{fetched.get('message', 'unknown')}")
    # The generic FDS hostname returned by getfileurl is readable from a Mac,
    # but AP01 reports mbedTLS -0x7100 while reading it.  Xiaomi's FDS object
    # namespace is also served by the official IoT OTA CDN used by the stock
    # AP01 firmware.  Keep the signed path/query and switch only the host.
    fds_url = str(result["url"])
    parsed = urlsplit(fds_url)
    ota_url = urlunsplit(
        (parsed.scheme, OTA_CDN_HOST, parsed.path, parsed.query, parsed.fragment)
    )

    probe_ota_url(ota_url)
    print(f"上传完成，已切换到 AP01 官方兼容 OTA CDN：{OTA_CDN_HOST}")
    return ota_url


def rpc_result(response: dict[str, Any]) -> Any:
    if response.get("code") != 0:
        return None
    return response.get("result")


def recent_ota_errors(cloud: MiCloud, did: str, since: int) -> list[str]:
    response = cloud.request(
        "user/get_user_device_data",
        {
            "did": did,
            "key": "ota_error",
            "type": "event",
            "time_start": since,
            "time_end": int(time.time()) + 5,
            "limit": 20,
        },
    )
    errors: list[str] = []
    for item in response.get("result") or []:
        value = str(item.get("value") or "")
        if value:
            errors.append(value)
    return errors


def deliver(
    cloud: MiCloud,
    firmware: Path,
    url: str,
    timeout: int,
    *,
    download_only: bool,
) -> None:
    device = cloud.ap01()
    did = str(device["did"])
    checksum = md5_file(firmware)
    proc = "dnld" if download_only else "dnld install"
    params: dict[str, Any] = {
        "app_url": url,
        "file_md5": checksum,
        "proc": proc,
        "mode": "normal",
        "signed_file": False,
        "original_length": firmware.stat().st_size,
    }
    if not download_only:
        params["install"] = "1"
    dispatch_time = int(time.time()) - 5
    accepted = cloud.rpc(did, "miIO.ota", params)
    if accepted.get("code") != 0 or "ok" not in (accepted.get("result") or []):
        raise RuntimeError(f"AP01 未接受 OTA：code={accepted.get('code')}")
    if download_only:
        print("设备已接受 OTA 下载测试；本次不安装、不切换启动分区…")
    else:
        print("设备已接受 OTA，等待下载和重启…")

    started = time.monotonic()
    last = None
    saw_offline = False
    saw_install_stage = False
    initial_life: int | None = None
    while time.monotonic() - started < timeout:
        elapsed = int(time.monotonic() - started)
        try:
            state = rpc_result(cloud.rpc(did, "miIO.get_ota_state"))
            progress = rpc_result(cloud.rpc(did, "miIO.get_ota_progress"))
            info = rpc_result(cloud.rpc(did, "miIO.info"))
            life = info.get("life") if isinstance(info, dict) else None
            if initial_life is None and isinstance(life, int):
                initial_life = life
            line = (state, progress, life)
            if line != last:
                print(f"[{elapsed:>3}s] state={state} progress={progress} life={life}")
                last = line
            progress_value = (
                progress[0]
                if isinstance(progress, list) and progress
                else progress
            )
            state_value = state[0] if isinstance(state, list) and state else state
            if state_value in ("installing", "installed") or progress_value == 100:
                saw_install_stage = True
            # AP01 resets the OTA progress field to 101 after a successful
            # install/reboot too.  A decreased uptime after observing the
            # install stage is stronger evidence than that stale marker.
            if (
                not download_only
                and saw_install_stage
                and isinstance(life, int)
                and initial_life is not None
                and life < initial_life
            ):
                print("AP01 已完成安装、重启并重新上线")
                return
            if progress_value == 101:
                errors = recent_ota_errors(cloud, did, dispatch_time)
                if errors:
                    raise RuntimeError(f"AP01 OTA 失败（progress=101）：{errors[0]}")
                if download_only or not saw_install_stage:
                    raise RuntimeError(
                        "AP01 OTA 返回 progress=101，但没有 ota_error 明细"
                    )
            if download_only and (
                state_value == "downloaded"
                or (isinstance(progress_value, int) and progress_value == 100)
            ):
                print("下载校验已完成；镜像尚未安装")
                return
        except (requests.RequestException, ValueError):
            saw_offline = True
        time.sleep(2)
    print("轮询结束；请在米家中确认设备在线，然后旋钮切到虚拟形象页")


def main() -> None:
    parser = argparse.ArgumentParser(description="自定义酷态科 AP01 的虚拟形象屏幕")
    parser.add_argument("gif", type=Path, help="320x240 GIF（不超过 221445 字节）")
    parser.add_argument("--firmware", type=Path, help="官方 AP01 固件 BIN")
    parser.add_argument("--output", type=Path, default=ARTIFACTS / "ap01-custom.bin")
    parser.add_argument(
        "--install",
        action="store_true",
        help="实验：通过小米云下发并轮询激活状态",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="仅验证 OTA CDN 下载与 MD5，不安装镜像",
    )
    parser.add_argument("--fds-did", help="显式指定具备 FDS 能力的网关 DID")
    parser.add_argument("--fds-model", help="显式指定具备 FDS 能力的网关 model")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    if args.install and args.download_only:
        parser.error("--install 和 --download-only 不能同时使用")
    if bool(args.fds_did) != bool(args.fds_model):
        parser.error("--fds-did 和 --fds-model 必须同时提供")
    cloud = MiCloud() if args.install or args.download_only or args.firmware is None else None
    source = args.firmware
    if source is None:
        source = ARTIFACTS / "ap01-1.0.2_0031.bin"
        if not source.exists():
            assert cloud is not None
            source = cloud.download_firmware(ARTIFACTS)
    build_firmware(source, args.gif, args.output)
    if not args.install and not args.download_only:
        print("已完成构建并刷新 AP01 Recovery 长度/CRC 元数据")
        return
    assert cloud is not None
    url = upload_to_xiaomi(
        cloud,
        args.output,
        fds_did=args.fds_did,
        fds_model=args.fds_model,
    )
    deliver(
        cloud,
        args.output,
        url,
        args.timeout,
        download_only=args.download_only,
    )


if __name__ == "__main__":
    main()
