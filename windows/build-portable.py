#!/usr/bin/env python3
"""Build a self-contained Windows x64 ZIP from macOS/Linux or Windows.

The release embeds the official CPython Windows runtime plus Windows wheels.
It is intentionally separate from PyInstaller so maintainers can produce a
usable Windows package even when no Windows runner is available.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


PYTHON_VERSION = "3.12.10"
PYTHON_SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
WINDOWS_PACKAGES = (
    "PySide6-Essentials==6.11.1",
    "Pillow==12.3.0",
    "requests==2.34.2",
    "cryptography==49.0.0",
)
RUNTIME_MODULES = (
    "ap01_prepare_screen.py",
    "ap01_screen_bridge.py",
    "ap01_wifi_bridge.py",
    "quota_dashboard.py",
    "ap01_custom_ota.py",
    "ap01_install_firmware.py",
    "ap01_fds_relay_client.py",
    "mi_cloud.py",
    "patch_asset.py",
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def download(url: str, target: Path, expected: str | None = None) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and (expected is None or digest(target) == expected):
        return target
    temporary = target.with_suffix(target.suffix + ".part")
    print(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output)
    if expected and digest(temporary) != expected:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"SHA-256 mismatch for {url}")
    os.replace(temporary, target)
    return target


def install_wheel(wheel: Path, destination: Path) -> None:
    """Extract wheel code plus purelib/platlib payload into site-packages."""

    with zipfile.ZipFile(wheel) as archive:
        for item in archive.infolist():
            name = item.filename
            if ".data/purelib/" in name:
                name = name.split(".data/purelib/", 1)[1]
            elif ".data/platlib/" in name:
                name = name.split(".data/platlib/", 1)[1]
            elif ".data/" in name:
                continue
            if not name or name.endswith("/"):
                continue
            target = (destination / name).resolve()
            if destination.resolve() not in target.parents:
                raise RuntimeError(f"unsafe wheel member: {item.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def build_icon(root: Path, output: Path) -> None:
    from PIL import Image

    image = Image.open(root / "macos/AP01Logo.png").convert("RGBA")
    image.save(
        output,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


def build_launcher(root: Path, app: Path, version: str) -> None:
    compiler = shutil.which("x86_64-w64-mingw32-gcc")
    windres = shutil.which("x86_64-w64-mingw32-windres")
    if not compiler or not windres:
        raise RuntimeError("mingw-w64 is required to build the Windows launcher")
    icon = app / "CUKTECHScreenController.ico"
    build_icon(root, icon)
    numbers = [int(value) for value in version.split(".")]
    numbers = (numbers + [0, 0, 0, 0])[:4]
    rc = app / "launcher.rc"
    rc.write_text(
        f'''1 ICON "{icon.as_posix()}"
1 VERSIONINFO
FILEVERSION {','.join(map(str, numbers))}
PRODUCTVERSION {','.join(map(str, numbers))}
FILEOS 0x40004
FILETYPE 0x1
BEGIN
  BLOCK "StringFileInfo"
  BEGIN
    BLOCK "080404b0"
    BEGIN
      VALUE "CompanyName", "wqytommy666\\0"
      VALUE "FileDescription", "CUKTECH AP01 Screen Controller\\0"
      VALUE "FileVersion", "{version}\\0"
      VALUE "OriginalFilename", "CUKTECH Screen Controller.exe\\0"
      VALUE "ProductName", "CUKTECH Screen Controller\\0"
      VALUE "ProductVersion", "{version}\\0"
    END
  END
  BLOCK "VarFileInfo"
  BEGIN
    VALUE "Translation", 0x0804, 1200
  END
END
''',
        encoding="utf-8",
    )
    resource = app / "launcher-resource.o"
    subprocess.run([windres, str(rc), str(resource)], check=True)
    output = app / "CUKTECH Screen Controller.exe"
    subprocess.run(
        [
            compiler,
            "-O2",
            "-s",
            "-municode",
            "-mwindows",
            "-static",
            str(root / "windows/launcher.c"),
            str(resource),
            "-o",
            str(output),
        ],
        check=True,
    )
    rc.unlink()
    resource.unlink()
    icon.unlink()
    if output.read_bytes()[:2] != b"MZ":
        raise RuntimeError("launcher is not a Windows PE executable")


def copy_application(root: Path, app_source: Path) -> None:
    for name in RUNTIME_MODULES:
        shutil.copy2(root / name, app_source / name)
    package = app_source / "windows"
    package.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "AP01ScreenController.py", "runtime.py", "ui.py"):
        shutil.copy2(root / "windows" / name, package / name)
    (app_source / "macos").mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "macos/AP01Logo.png", app_source / "macos/AP01Logo.png")
    shutil.copytree(
        root / "reference/provider-icons",
        app_source / "reference/provider-icons",
        dirs_exist_ok=True,
    )
    shutil.copy2(root / "LICENSE", app_source / "PROJECT-LICENSE.txt")


def create_zip(stage: Path, output: Path) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                archive.write(path, Path(stage.name) / path.relative_to(stage))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="0.4.1")
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache/cuktech-windows-build")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output_dir = (args.output_dir or root / "dist").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stage_name = f"CUKTECH-Screen-Controller-{args.version}-Windows-x64"
    stage = output_dir / stage_name
    if stage.exists():
        shutil.rmtree(stage)
    app = stage / "App"
    site_packages = app / "Lib/site-packages"
    app_source = app / "app"
    site_packages.mkdir(parents=True, exist_ok=True)
    app_source.mkdir(parents=True, exist_ok=True)

    python_zip = download(
        f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip",
        args.cache / f"python-{PYTHON_VERSION}-embed-amd64.zip",
        PYTHON_SHA256,
    )
    with zipfile.ZipFile(python_zip) as archive:
        archive.extractall(app)
    shutil.copy2(app / "pythonw.exe", app / "CUKTECHRuntime.exe")
    (app / "python312._pth").write_text(
        "python312.zip\n.\nLib\\site-packages\napp\nimport site\n",
        encoding="ascii",
    )

    lock_key = hashlib.sha256("|".join(WINDOWS_PACKAGES).encode()).hexdigest()[:12]
    wheel_dir = args.cache / f"wheels-cp312-{lock_key}"
    wheel_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--disable-pip-version-check",
            "--dest",
            str(wheel_dir),
            "--only-binary=:all:",
            "--platform",
            "win_amd64",
            "--python-version",
            "3.12",
            "--implementation",
            "cp",
            *WINDOWS_PACKAGES,
        ],
        check=True,
    )
    for wheel in sorted(wheel_dir.glob("*.whl")):
        install_wheel(wheel, site_packages)

    copy_application(root, app_source)
    build_launcher(root, app, args.version)
    shutil.copy2(root / "windows/THIRD-PARTY-NOTICES.txt", app / "THIRD-PARTY-NOTICES.txt")
    for name in (
        "Install CUKTECH Screen Controller.cmd",
        "Install-CUKTECHScreenController.ps1",
        "Uninstall-CUKTECHScreenController.ps1",
        "先读我-Windows.txt",
        "mi-credentials.example.json",
    ):
        shutil.copy2(root / "windows" / name, stage / name)
    shutil.copy2(root / "windows/THIRD-PARTY-NOTICES.txt", stage / "THIRD-PARTY-NOTICES.txt")
    shutil.copy2(root / "LICENSE", stage / "PROJECT-LICENSE.txt")
    readme = stage / "先读我-Windows.txt"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace("{{VERSION}}", args.version),
        encoding="utf-8-sig",
    )
    installer = stage / "Install-CUKTECHScreenController.ps1"
    installer.write_text(
        installer.read_text(encoding="utf-8").replace("{{VERSION}}", args.version),
        encoding="utf-8-sig",
    )
    manifest = {
        "name": "CUKTECH Screen Controller",
        "version": args.version,
        "platform": "Windows x64",
        "python": PYTHON_VERSION,
        "python_sha256": PYTHON_SHA256,
        "packages": list(WINDOWS_PACKAGES),
    }
    (stage / "BUILD-MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    output = output_dir / f"{stage_name}.zip"
    output.unlink(missing_ok=True)
    create_zip(stage, output)
    checksum = digest(output)
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{checksum}  {output.name}\n", encoding="ascii"
    )
    print(output)
    print(f"SHA-256 {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
