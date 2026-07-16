#!/usr/bin/env python3
"""Build and verify an offline AP01 real-time GIF firmware patch.

The generated image reuses the stock weather timer and NuttX webclient to GET
``/screen.gif`` from a local HTTP bridge.  The payload streams the response to
one of three RAM-backed tmpfs slots and publishes a checksummed metadata record
only after HTTP 200 and GIF validation.  A wrapper around the stock one-second
LVGL timer applies a newly published slot on the UI thread.

This program is intentionally an *offline-only* builder.  It contains no OTA,
cloud, socket, serial, or device-install operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


HERE = Path(__file__).resolve().parent
PAYLOAD_DIR = HERE / "realtime_payload"
PAYLOAD_SOURCE = PAYLOAD_DIR / "ap01_realtime_payload.c"
PAYLOAD_LINKER = PAYLOAD_DIR / "ap01_realtime_payload.ld"
DEFAULT_INPUT = HERE / "artifacts" / "ap01-1.0.2_0031-screen-compat.bin"
DEFAULT_OUTPUT = HERE / "artifacts" / "ap01-1.0.2_0031-screen-realtime.bin"
DEFAULT_BUILD_DIR = HERE / "artifacts" / "realtime-build"
DEFAULT_URL = "http://192.168.1.100:8765/screen.gif"

FIRMWARE_SIZE = 6_804_520
XIP_DELTA = 0x9FFFF000
RECOVERY_TAG = b"0x5245434f56455259544147"

PET0_DESCRIPTOR = 0x1F8090
PET0_DATA = 0x1F80AC
PET0_SLOT_END = 0x2563D6
PAYLOAD_OFFSET = 0x230000
PAYLOAD_VA = XIP_DELTA + PAYLOAD_OFFSET

TRAMPOLINE_OFFSET = 0x01C008
TRAMPOLINE_SIZE = 8

UI_CALLBACK_LUI = 0x0B37E4
UI_CALLBACK_ADDI = 0x0B37EE
SINK_CALLBACK_LUI = 0x0B7D92
SINK_CALLBACK_ADDI = 0x0B7D96
HTTP_PERFORM_CALL = 0x0B82C0

SUCCESS_TIMER_LUI = 0x0B7F86
SUCCESS_TIMER_ADDI = 0x0B7F8A
SUCCESS_TIMER_REM = 0x0B7F8E
SUCCESS_TIMER_BASE_ADDI = 0x0B7F92
SUCCESS_TIMER_ADD = 0x0B7FB0
FAILURE_BACKOFF_STORE = 0x0B7D5A

URL_REGIONS = (
    (0x1EE968, 40, b"https://iot.cuktech.net/api/weather2?", "base-location-id"),
    (0x1EE990, 44, b"%slocid=%s&mac=%s&timestamp=%lld&token=%s", "format-location-id"),
    (0x1EEA00, 40, b"https://iot.cuktech.net/api/weather?", "base-city"),
    (0x1EEA28, 48, b"%scity=%s&adm=%s&mac=%s&timestamp=%lld&token=%s", "format-city"),
)

EXPECTED = {
    UI_CALLBACK_LUI: bytes.fromhex("37b50ba0"),
    UI_CALLBACK_ADDI: bytes.fromhex("1305a55d"),
    SINK_CALLBACK_LUI: bytes.fromhex("b7670ba0"),
    SINK_CALLBACK_ADDI: bytes.fromhex("9387672d"),
    HTTP_PERFORM_CALL: bytes.fromhex("ef10a23f"),
    SUCCESS_TIMER_LUI: bytes.fromhex("b7f73600"),
    SUCCESS_TIMER_ADDI: bytes.fromhex("138917e8"),
    SUCCESS_TIMER_REM: bytes.fromhex("33692503"),
    SUCCESS_TIMER_BASE_ADDI: bytes.fromhex("938707e8"),
    SUCCESS_TIMER_ADD: bytes.fromhex("3e99"),
    FAILURE_BACKOFF_STORE: bytes.fromhex("23a6f9cc"),
}

REQUIRED_PAYLOAD_SYMBOLS = (
    "ap01_quota_sink",
    "ap01_quota_webclient_wrapper",
    "ap01_quota_ui_timer_wrapper",
)

VERIFIED_FIRMWARE_CALLEES = (
    0xA00BB5DA,  # stock one-second UI callback
    0xA00C5D84,  # lv_window_slider_get_win_obj_by_idx
    0xA00CF8D8,  # lv_gif_set_src
    0xA00D86BA,  # webclient_perform
    0xA003F448,  # open
    0xA0026788,  # close
    0xA003F5F4,  # read
    0xA0027D94,  # write
)


@dataclass(frozen=True)
class PayloadBuild:
    binary: Path
    elf: Path
    object: Path
    map_file: Path
    disassembly: Path
    readelf: Path
    symbols: dict[str, int]
    size: int
    sha256: str


def sha256_bytes(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def md5_bytes(data: bytes | bytearray) -> str:
    return hashlib.md5(data).hexdigest()


def recovery_crc(data: bytes | bytearray) -> int:
    return (zlib.crc32(data, 0xFFFFFFFF) ^ 0xFFFFFFFF) & 0xFFFFFFFF


def validate_recovery_trailer(firmware: bytes | bytearray) -> tuple[int, int]:
    marker = firmware.rfind(RECOVERY_TAG)
    if marker < 0 or marker + 40 != len(firmware):
        raise RuntimeError("invalid AP01 RECOVERYTAG trailer")
    if firmware.find(RECOVERY_TAG) == marker:
        raise RuntimeError("expected both AP01 RECOVERYTAG markers")
    stored_length = struct.unpack_from(">I", firmware, marker + 32)[0]
    stored_crc = struct.unpack_from("<I", firmware, marker + 36)[0]
    calculated = recovery_crc(firmware[:-4])
    if stored_length != len(firmware):
        raise RuntimeError("RECOVERYTAG length mismatch")
    if stored_crc != calculated:
        raise RuntimeError("RECOVERYTAG CRC mismatch")
    return marker, stored_crc


def refresh_recovery_trailer(firmware: bytearray) -> int:
    marker = firmware.rfind(RECOVERY_TAG)
    if marker < 0 or marker + 40 != len(firmware):
        raise RuntimeError("invalid AP01 RECOVERYTAG trailer")
    struct.pack_into(">I", firmware, marker + 32, len(firmware))
    checksum = recovery_crc(firmware[:-4])
    struct.pack_into("<I", firmware, marker + 36, checksum)
    validate_recovery_trailer(firmware)
    return checksum


def encode_lui(rd: int, high20: int) -> bytes:
    if not 0 <= rd <= 31:
        raise ValueError("invalid register")
    return struct.pack("<I", ((high20 & 0xFFFFF) << 12) | (rd << 7) | 0x37)


def encode_addi(rd: int, rs1: int, immediate: int) -> bytes:
    if not (0 <= rd <= 31 and 0 <= rs1 <= 31):
        raise ValueError("invalid register")
    if not -2048 <= immediate <= 2047:
        raise ValueError("ADDI immediate out of range")
    word = (
        ((immediate & 0xFFF) << 20)
        | (rs1 << 15)
        | (rd << 7)
        | 0x13
    )
    return struct.pack("<I", word)


def encode_jalr(rd: int, rs1: int, immediate: int) -> bytes:
    if not (0 <= rd <= 31 and 0 <= rs1 <= 31):
        raise ValueError("invalid register")
    if not -2048 <= immediate <= 2047:
        raise ValueError("JALR immediate out of range")
    word = (
        ((immediate & 0xFFF) << 20)
        | (rs1 << 15)
        | (rd << 7)
        | 0x67
    )
    return struct.pack("<I", word)


def split_absolute(address: int) -> tuple[int, int]:
    low = address & 0xFFF
    if low >= 0x800:
        low -= 0x1000
    high = (address - low) >> 12
    return high, low


def absolute_lui_addi(address: int, rd: int) -> tuple[bytes, bytes]:
    high, low = split_absolute(address)
    return encode_lui(rd, high), encode_addi(rd, rd, low)


def absolute_tail_jump(address: int, scratch: int = 5) -> bytes:
    high, low = split_absolute(address)
    return encode_lui(scratch, high) + encode_jalr(0, scratch, low)


def encode_jal(source_address: int, target_address: int, rd: int = 1) -> bytes:
    offset = target_address - source_address
    if offset & 1:
        raise ValueError("JAL target must be two-byte aligned")
    if not -(1 << 20) <= offset < (1 << 20):
        raise ValueError("JAL target is outside +/-1 MiB")
    immediate = offset & 0x1FFFFF
    word = (
        (((immediate >> 20) & 0x1) << 31)
        | (((immediate >> 1) & 0x3FF) << 21)
        | (((immediate >> 11) & 0x1) << 20)
        | (((immediate >> 12) & 0xFF) << 12)
        | (rd << 7)
        | 0x6F
    )
    return struct.pack("<I", word)


def decode_jal_target(instruction: bytes, source_address: int) -> tuple[int, int]:
    if len(instruction) != 4:
        raise ValueError("JAL instruction must be four bytes")
    word = struct.unpack("<I", instruction)[0]
    if word & 0x7F != 0x6F:
        raise ValueError("instruction is not JAL")
    rd = (word >> 7) & 0x1F
    immediate = (
        ((word >> 31) & 1) << 20
        | ((word >> 21) & 0x3FF) << 1
        | ((word >> 20) & 1) << 11
        | ((word >> 12) & 0xFF) << 12
    )
    if immediate & (1 << 20):
        immediate -= 1 << 21
    return source_address + immediate, rd


def decode_absolute_pair(lui: bytes, second: bytes, expected_second_opcode: int) -> tuple[int, int, int]:
    first_word = struct.unpack("<I", lui)[0]
    second_word = struct.unpack("<I", second)[0]
    if first_word & 0x7F != 0x37:
        raise ValueError("first instruction is not LUI")
    if second_word & 0x7F != expected_second_opcode:
        raise ValueError("unexpected second instruction opcode")
    rd = (first_word >> 7) & 0x1F
    rs1 = (second_word >> 15) & 0x1F
    second_rd = (second_word >> 7) & 0x1F
    immediate = (second_word >> 20) & 0xFFF
    if immediate & 0x800:
        immediate -= 0x1000
    address = (first_word & 0xFFFFF000) + immediate
    return address & 0xFFFFFFFF, rd, (rs1 << 5) | second_rd


def command_path(prefix: str, suffix: str) -> str:
    executable = shutil.which(prefix + suffix)
    if not executable:
        raise RuntimeError(f"missing tool: {prefix + suffix}")
    return executable


def run(command: list[str], *, capture: bool = False) -> str:
    completed = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    return completed.stdout or ""


def parse_nm(output: str) -> tuple[dict[str, int], list[str]]:
    symbols: dict[str, int] = {}
    undefined: list[str] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "U":
            undefined.append(parts[1])
        elif len(parts) >= 3:
            try:
                address = int(parts[0], 16)
            except ValueError:
                continue
            symbols[parts[-1]] = address
    return symbols, undefined


def build_payload(build_dir: Path, tool_prefix: str = "riscv64-elf-") -> PayloadBuild:
    gcc = command_path(tool_prefix, "gcc")
    objcopy = command_path(tool_prefix, "objcopy")
    objdump = command_path(tool_prefix, "objdump")
    nm = command_path(tool_prefix, "nm")
    readelf_tool = command_path(tool_prefix, "readelf")

    build_dir.mkdir(parents=True, exist_ok=True)
    object_file = build_dir / "ap01_realtime_payload.o"
    elf_file = build_dir / "ap01_realtime_payload.elf"
    binary_file = build_dir / "ap01_realtime_payload.bin"
    map_file = build_dir / "ap01_realtime_payload.map"
    disassembly_file = build_dir / "ap01_realtime_payload.disasm.txt"
    readelf_file = build_dir / "ap01_realtime_payload.readelf.txt"

    common = ["-march=rv32imac", "-mabi=ilp32"]
    run(
        [
            gcc,
            *common,
            "-Os",
            "-ffreestanding",
            "-fno-builtin",
            "-fno-pic",
            "-fno-pie",
            "-fno-plt",
            "-fno-stack-protector",
            "-fno-asynchronous-unwind-tables",
            "-fno-unwind-tables",
            "-fno-jump-tables",
            "-fno-common",
            "-fno-toplevel-reorder",
            "-msmall-data-limit=0",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-c",
            str(PAYLOAD_SOURCE),
            "-o",
            str(object_file),
        ]
    )
    run(
        [
            gcc,
            *common,
            "-nostdlib",
            "-nostartfiles",
            "-nodefaultlibs",
            "-static",
            "-Wl,--build-id=none",
            "-Wl,--no-relax",
            f"-Wl,-Map,{map_file}",
            "-T",
            str(PAYLOAD_LINKER),
            str(object_file),
            "-o",
            str(elf_file),
        ]
    )
    run([objcopy, "-O", "binary", "-j", ".payload", str(elf_file), str(binary_file)])

    nm_output = run([nm, "-n", str(elf_file)], capture=True)
    symbols, undefined = parse_nm(nm_output)
    if undefined:
        raise RuntimeError(f"payload has undefined symbols: {', '.join(undefined)}")
    for name in REQUIRED_PAYLOAD_SYMBOLS:
        if name not in symbols:
            raise RuntimeError(f"payload symbol missing: {name}")

    payload = binary_file.read_bytes()
    if not payload:
        raise RuntimeError("empty payload")
    for name in REQUIRED_PAYLOAD_SYMBOLS:
        address = symbols[name]
        if not PAYLOAD_VA <= address < PAYLOAD_VA + len(payload):
            raise RuntimeError(f"payload symbol outside binary: {name}=0x{address:08x}")

    disassembly = run(
        [objdump, "-d", "-M", "no-aliases,numeric", str(elf_file)], capture=True
    )
    for address in VERIFIED_FIRMWARE_CALLEES:
        if f"{address:08x}" not in disassembly.lower():
            raise RuntimeError(f"verified firmware callee missing from disassembly: 0x{address:08x}")
    disassembly_file.write_text(disassembly)

    readelf_output = run(
        [readelf_tool, "-h", "-S", "-s", "-r", str(elf_file)], capture=True
    )
    if "There are no relocations in this file." not in readelf_output:
        raise RuntimeError("payload ELF unexpectedly contains relocations")
    readelf_file.write_text(readelf_output)

    symbol_manifest = {
        "payload_va": f"0x{PAYLOAD_VA:08x}",
        "size": len(payload),
        "sha256": sha256_bytes(payload),
        "symbols": {
            name: f"0x{address:08x}" for name, address in sorted(symbols.items())
        },
        "verified_firmware_callees": [f"0x{x:08x}" for x in VERIFIED_FIRMWARE_CALLEES],
        "relocations": 0,
        "writable_globals": 0,
    }
    (build_dir / "ap01_realtime_payload_symbols.json").write_text(
        json.dumps(symbol_manifest, indent=2, sort_keys=True) + "\n"
    )

    return PayloadBuild(
        binary=binary_file,
        elf=elf_file,
        object=object_file,
        map_file=map_file,
        disassembly=disassembly_file,
        readelf=readelf_file,
        symbols=symbols,
        size=len(payload),
        sha256=sha256_bytes(payload),
    )


def require_bytes(firmware: bytes | bytearray, offset: int, expected: bytes, label: str) -> None:
    actual = bytes(firmware[offset : offset + len(expected)])
    if actual != expected:
        raise RuntimeError(
            f"{label} mismatch at 0x{offset:x}: expected {expected.hex()}, got {actual.hex()}"
        )


def patch_region(firmware: bytearray, offset: int, capacity: int, value: bytes) -> None:
    if len(value) + 1 > capacity:
        raise RuntimeError(
            f"replacement needs {len(value) + 1} bytes, region at 0x{offset:x} has {capacity}"
        )
    firmware[offset : offset + capacity] = value + b"\0" * (capacity - len(value))


def offset_in_ranges(offset: int, ranges: Iterable[tuple[int, int]]) -> bool:
    return any(start <= offset < end for start, end in ranges)


def changed_ranges(before: bytes | bytearray, after: bytes | bytearray) -> list[tuple[int, int]]:
    if len(before) != len(after):
        raise ValueError("cannot diff different-sized images")
    result: list[tuple[int, int]] = []
    start: int | None = None
    for index, (left, right) in enumerate(zip(before, after)):
        if left != right and start is None:
            start = index
        elif left == right and start is not None:
            result.append((start, index))
            start = None
    if start is not None:
        result.append((start, len(before)))
    return result


def validate_source(firmware: bytes, payload_size: int) -> dict[str, int]:
    if len(firmware) != FIRMWARE_SIZE:
        raise RuntimeError(f"unexpected firmware size: {len(firmware)}")
    if firmware[:4] != b"BFNP":
        raise RuntimeError("input does not have a BFNP header")
    validate_recovery_trailer(firmware)

    gif_size = struct.unpack_from("<I", firmware, PET0_DESCRIPTOR + 12)[0]
    gif_pointer = struct.unpack_from("<I", firmware, PET0_DESCRIPTOR + 16)[0]
    gif_end = PET0_DATA + gif_size
    if gif_pointer != XIP_DELTA + PET0_DATA:
        raise RuntimeError("pet0 descriptor pointer mismatch")
    if gif_end > PAYLOAD_OFFSET:
        raise RuntimeError(
            f"pet0 GIF ends at 0x{gif_end:x}, overlapping payload 0x{PAYLOAD_OFFSET:x}; "
            "use the shortened compatibility image"
        )
    if PAYLOAD_OFFSET + payload_size > PET0_SLOT_END:
        raise RuntimeError("payload exceeds the original pet0 resource slot")
    if any(firmware[PAYLOAD_OFFSET : PAYLOAD_OFFSET + payload_size]):
        raise RuntimeError("payload target is not zero-filled")
    if any(firmware[TRAMPOLINE_OFFSET : TRAMPOLINE_OFFSET + TRAMPOLINE_SIZE]):
        raise RuntimeError("reviewed near trampoline cave is not zero-filled")

    for offset, expected in EXPECTED.items():
        require_bytes(firmware, offset, expected, "stock instruction")
    for offset, _capacity, original, label in URL_REGIONS:
        require_bytes(firmware, offset, original + b"\0", label)

    return {"pet0_gif_size": gif_size, "pet0_gif_end": gif_end}


def build_firmware(
    source: Path,
    output: Path,
    build_dir: Path,
    *,
    url: str = DEFAULT_URL,
    refresh_seconds: int = 300,
    tool_prefix: str = "riscv64-elf-",
) -> dict[str, object]:
    try:
        url_bytes = url.encode("ascii")
    except UnicodeEncodeError as error:
        raise RuntimeError("URL must be ASCII") from error
    if not url.startswith("http://"):
        raise RuntimeError("this patch hooks the verified plain-HTTP path; URL must start with http://")
    if len(url_bytes) + 1 > 40:
        raise RuntimeError("URL is too long for both stock 40-byte base-string regions")
    if not 10 <= refresh_seconds <= 7200:
        raise RuntimeError("refresh interval must be between 10 and 7200 seconds")
    refresh_ms = refresh_seconds * 1000

    payload_build = build_payload(build_dir, tool_prefix)
    payload = payload_build.binary.read_bytes()
    original = source.read_bytes()
    source_info = validate_source(original, len(payload))
    firmware = bytearray(original)

    # Both weather location branches now sprintf("%s", local_url).
    for offset, capacity, _old, label in URL_REGIONS:
        replacement = url_bytes if label.startswith("base-") else b"%s"
        patch_region(firmware, offset, capacity, replacement)

    sink_va = payload_build.symbols["ap01_quota_sink"]
    web_wrapper_va = payload_build.symbols["ap01_quota_webclient_wrapper"]
    ui_wrapper_va = payload_build.symbols["ap01_quota_ui_timer_wrapper"]

    sink_lui, sink_addi = absolute_lui_addi(sink_va, rd=15)  # a5
    ui_lui, ui_addi = absolute_lui_addi(ui_wrapper_va, rd=10)  # a0
    firmware[SINK_CALLBACK_LUI : SINK_CALLBACK_LUI + 4] = sink_lui
    firmware[SINK_CALLBACK_ADDI : SINK_CALLBACK_ADDI + 4] = sink_addi
    firmware[UI_CALLBACK_LUI : UI_CALLBACK_LUI + 4] = ui_lui
    firmware[UI_CALLBACK_ADDI : UI_CALLBACK_ADDI + 4] = ui_addi

    trampoline = absolute_tail_jump(web_wrapper_va)
    if len(trampoline) != TRAMPOLINE_SIZE:
        raise AssertionError("unexpected trampoline size")
    firmware[TRAMPOLINE_OFFSET : TRAMPOLINE_OFFSET + TRAMPOLINE_SIZE] = trampoline
    firmware[HTTP_PERFORM_CALL : HTTP_PERFORM_CALL + 4] = encode_jal(
        XIP_DELTA + HTTP_PERFORM_CALL,
        XIP_DELTA + TRAMPOLINE_OFFSET,
        rd=1,
    )

    # Replace random 1-2 hour success delay with a fixed refresh interval.
    timer_lui, timer_addi = absolute_lui_addi(refresh_ms, rd=18)  # s2
    firmware[SUCCESS_TIMER_LUI : SUCCESS_TIMER_LUI + 4] = timer_lui
    firmware[SUCCESS_TIMER_ADDI : SUCCESS_TIMER_ADDI + 4] = timer_addi
    firmware[SUCCESS_TIMER_REM : SUCCESS_TIMER_REM + 4] = bytes.fromhex("13000000")
    firmware[SUCCESS_TIMER_BASE_ADDI : SUCCESS_TIMER_BASE_ADDI + 4] = bytes.fromhex("13000000")
    firmware[SUCCESS_TIMER_ADD : SUCCESS_TIMER_ADD + 2] = bytes.fromhex("0100")

    # Stock failure handling doubles a RAM retry interval from 30 seconds up
    # to two hours.  Keep its initialized 30-second value by suppressing only
    # the final store of the doubled value; the existing timer and log paths
    # remain untouched.
    firmware[FAILURE_BACKOFF_STORE : FAILURE_BACKOFF_STORE + 4] = bytes.fromhex(
        "13000000"
    )

    firmware[PAYLOAD_OFFSET : PAYLOAD_OFFSET + len(payload)] = payload
    recovery_checksum = refresh_recovery_trailer(firmware)

    recovery_marker = firmware.rfind(RECOVERY_TAG)
    allowed_ranges = [
        (PAYLOAD_OFFSET, PAYLOAD_OFFSET + len(payload)),
        (TRAMPOLINE_OFFSET, TRAMPOLINE_OFFSET + TRAMPOLINE_SIZE),
        (UI_CALLBACK_LUI, UI_CALLBACK_LUI + 4),
        (UI_CALLBACK_ADDI, UI_CALLBACK_ADDI + 4),
        (SINK_CALLBACK_LUI, SINK_CALLBACK_LUI + 4),
        (SINK_CALLBACK_ADDI, SINK_CALLBACK_ADDI + 4),
        (HTTP_PERFORM_CALL, HTTP_PERFORM_CALL + 4),
        (SUCCESS_TIMER_LUI, SUCCESS_TIMER_LUI + 4),
        (SUCCESS_TIMER_ADDI, SUCCESS_TIMER_ADDI + 4),
        (SUCCESS_TIMER_REM, SUCCESS_TIMER_REM + 4),
        (SUCCESS_TIMER_BASE_ADDI, SUCCESS_TIMER_BASE_ADDI + 4),
        (SUCCESS_TIMER_ADD, SUCCESS_TIMER_ADD + 2),
        (FAILURE_BACKOFF_STORE, FAILURE_BACKOFF_STORE + 4),
        (recovery_marker + 32, recovery_marker + 40),
    ]
    allowed_ranges.extend((offset, offset + capacity) for offset, capacity, _, _ in URL_REGIONS)
    differences = changed_ranges(original, firmware)
    for start, end in differences:
        for offset in range(start, end):
            if not offset_in_ranges(offset, allowed_ranges):
                raise RuntimeError(f"unexpected changed byte at 0x{offset:x}")

    verify_patched_image(
        firmware,
        payload,
        payload_build.symbols,
        url_bytes,
        refresh_ms,
        trampoline,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(firmware)

    manifest: dict[str, object] = {
        "offline_only": True,
        "input": str(source),
        "output": str(output),
        "input_size": len(original),
        "output_size": len(firmware),
        "input_sha256": sha256_bytes(original),
        "output_sha256": sha256_bytes(firmware),
        "output_md5": md5_bytes(firmware),
        "recovery_crc": f"0x{recovery_checksum:08x}",
        "url": url,
        "refresh_seconds": refresh_seconds,
        "failure_retry_seconds": 30,
        "payload": {
            "file_offset": f"0x{PAYLOAD_OFFSET:x}",
            "va": f"0x{PAYLOAD_VA:08x}",
            "size": len(payload),
            "sha256": payload_build.sha256,
            "symbols": {
                name: f"0x{payload_build.symbols[name]:08x}"
                for name in REQUIRED_PAYLOAD_SYMBOLS
            },
        },
        "trampoline": {
            "file_offset": f"0x{TRAMPOLINE_OFFSET:x}",
            "va": f"0x{XIP_DELTA + TRAMPOLINE_OFFSET:08x}",
            "bytes": trampoline.hex(),
            "target": f"0x{web_wrapper_va:08x}",
        },
        "source_layout": source_info,
        "changed_ranges": [
            {"start": f"0x{start:x}", "end_exclusive": f"0x{end:x}"}
            for start, end in differences
        ],
        "tmpfs_protocol": {
            "slots": [
                "/tmp/.ap01q0.gif",
                "/tmp/.ap01q1.gif",
                "/tmp/.ap01q2.gif",
            ],
            "metadata": "/tmp/.ap01q.meta",
            "ack": "/tmp/.ap01q.ack",
            "reason": "no verified rename ABI; three-slot published/applied exclusion with checksummed records",
        },
        "validation": {
            "http_status": 200,
            "gif_magic": ["GIF89a"],
            "dimensions": [320, 240],
            "minimum_bytes": 13,
            "maximum_bytes": 262144,
            "gif_trailer": "0x3b",
            "elf_relocations": 0,
            "writable_payload_globals": 0,
        },
    }
    manifest_path = build_dir / "ap01_realtime_patch_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def verify_patched_image(
    firmware: bytes | bytearray,
    payload: bytes,
    symbols: dict[str, int],
    url: bytes,
    refresh_ms: int,
    trampoline: bytes,
) -> None:
    if len(firmware) != FIRMWARE_SIZE or firmware[:4] != b"BFNP":
        raise RuntimeError("patched image header/size invalid")
    validate_recovery_trailer(firmware)
    require_bytes(firmware, PAYLOAD_OFFSET, payload, "payload readback")
    require_bytes(firmware, TRAMPOLINE_OFFSET, trampoline, "trampoline readback")

    for offset, capacity, _old, label in URL_REGIONS:
        replacement = url if label.startswith("base-") else b"%s"
        expected = replacement + b"\0" * (capacity - len(replacement))
        require_bytes(firmware, offset, expected, label + " readback")

    sink_address, sink_rd, sink_regs = decode_absolute_pair(
        firmware[SINK_CALLBACK_LUI : SINK_CALLBACK_LUI + 4],
        firmware[SINK_CALLBACK_ADDI : SINK_CALLBACK_ADDI + 4],
        0x13,
    )
    if sink_address != symbols["ap01_quota_sink"] or sink_rd != 15 or sink_regs != (15 << 5) | 15:
        raise RuntimeError("sink callback absolute pointer verification failed")

    ui_address, ui_rd, ui_regs = decode_absolute_pair(
        firmware[UI_CALLBACK_LUI : UI_CALLBACK_LUI + 4],
        firmware[UI_CALLBACK_ADDI : UI_CALLBACK_ADDI + 4],
        0x13,
    )
    if ui_address != symbols["ap01_quota_ui_timer_wrapper"] or ui_rd != 10 or ui_regs != (10 << 5) | 10:
        raise RuntimeError("UI callback absolute pointer verification failed")

    call_target, call_rd = decode_jal_target(
        bytes(firmware[HTTP_PERFORM_CALL : HTTP_PERFORM_CALL + 4]),
        XIP_DELTA + HTTP_PERFORM_CALL,
    )
    if call_target != XIP_DELTA + TRAMPOLINE_OFFSET or call_rd != 1:
        raise RuntimeError("HTTP call-site trampoline verification failed")

    trampoline_address, trampoline_rd, trampoline_regs = decode_absolute_pair(
        bytes(firmware[TRAMPOLINE_OFFSET : TRAMPOLINE_OFFSET + 4]),
        bytes(firmware[TRAMPOLINE_OFFSET + 4 : TRAMPOLINE_OFFSET + 8]),
        0x67,
    )
    if (
        trampoline_address != symbols["ap01_quota_webclient_wrapper"]
        or trampoline_rd != 5
        or trampoline_regs != (5 << 5) | 0
    ):
        raise RuntimeError("far trampoline target verification failed")

    timer_lui, timer_addi = absolute_lui_addi(refresh_ms, rd=18)
    require_bytes(firmware, SUCCESS_TIMER_LUI, timer_lui, "refresh LUI")
    require_bytes(firmware, SUCCESS_TIMER_ADDI, timer_addi, "refresh ADDI")
    require_bytes(firmware, SUCCESS_TIMER_REM, bytes.fromhex("13000000"), "refresh nop 1")
    require_bytes(
        firmware,
        SUCCESS_TIMER_BASE_ADDI,
        bytes.fromhex("13000000"),
        "refresh nop 2",
    )
    require_bytes(firmware, SUCCESS_TIMER_ADD, bytes.fromhex("0100"), "refresh c.nop")
    require_bytes(
        firmware,
        FAILURE_BACKOFF_STORE,
        bytes.fromhex("13000000"),
        "failure backoff store nop",
    )


def print_summary(manifest: dict[str, object], build_dir: Path) -> None:
    payload = manifest["payload"]
    assert isinstance(payload, dict)
    print(f"input:        {manifest['input']}")
    print(f"output:       {manifest['output']}")
    print(f"URL:          {manifest['url']}")
    print(f"refresh:      {manifest['refresh_seconds']} seconds")
    print(
        f"payload:      {payload['size']} bytes at file {payload['file_offset']} / VA {payload['va']}"
    )
    print(f"Recovery CRC: {manifest['recovery_crc']}")
    print(f"MD5:          {manifest['output_md5']}")
    print(f"build report: {build_dir / 'ap01_realtime_patch_manifest.json'}")
    print("offline build complete; nothing was uploaded or installed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--refresh-seconds", type=int, default=300)
    parser.add_argument("--tool-prefix", default="riscv64-elf-")
    args = parser.parse_args(argv)

    manifest = build_firmware(
        args.input,
        args.output,
        args.build_dir,
        url=args.url,
        refresh_seconds=args.refresh_seconds,
        tool_prefix=args.tool_prefix,
    )
    print_summary(manifest, args.build_dir)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
