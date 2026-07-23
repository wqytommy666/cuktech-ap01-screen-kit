#!/bin/zsh
set -euo pipefail

HERE="${0:A:h}"
ROOT="${HERE:h}"
RUNTIME_ROOT="${CUKTECH_PROJECT_ROOT:-$ROOT}"
if [[ "${CUKTECH_PORTABLE:-0}" == "1" ]]; then
    RUNTIME_ROOT=""
fi
LAUNCH_LABEL="${CUKTECH_LAUNCH_LABEL:-io.github.wqytommy666.cuktech-screen-controller.bridge}"
APP_VERSION="${CUKTECH_VERSION:-0.4.1}"
APP_BUILD="${CUKTECH_BUILD:-7}"
ICON_PYTHON="${CUKTECH_PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$ICON_PYTHON" ]]; then
    ICON_PYTHON="$(command -v python3 || true)"
fi
if [[ -z "$ICON_PYTHON" ]] || ! "$ICON_PYTHON" -c 'import PIL' >/dev/null 2>&1; then
    echo "Pillow is required to build the macOS icon (set CUKTECH_PYTHON)." >&2
    exit 1
fi
APP="$ROOT/dist/CUKTECH Screen Controller.app"
CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
MODULE_CACHE="$ROOT/.build/ModuleCache"

mkdir -p "$MACOS" "$RESOURCES" "$MODULE_CACHE"
xcrun swiftc \
    -parse-as-library \
    -O \
    -target arm64-apple-macosx14.0 \
    -module-cache-path "$MODULE_CACHE" \
    -framework SwiftUI \
    -framework AppKit \
    -framework Foundation \
    "$HERE/AP01ScreenController.swift" \
    -o "$MACOS/AP01ScreenController"

cp "$HERE/AP01Logo.png" "$RESOURCES/AP01Logo.png"
"$ICON_PYTHON" - "$HERE/AP01Logo.png" "$RESOURCES/CUKTECHScreenController.icns" <<'PY'
import sys
from PIL import Image

source, output = sys.argv[1:]
image = Image.open(source).convert("RGBA")
image.save(
    output,
    format="ICNS",
    sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)],
)
PY

cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>CFBundleDisplayName</key><string>CUKTECH Screen Controller</string>
    <key>CFBundleExecutable</key><string>AP01ScreenController</string>
    <key>CFBundleIconFile</key><string>CUKTECHScreenController.icns</string>
    <key>CFBundleIdentifier</key><string>com.wqytommy.CUKTECHScreenController</string>
    <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
    <key>CFBundleName</key><string>CUKTECH Screen Controller</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>${APP_VERSION}</string>
    <key>CFBundleVersion</key><string>${APP_BUILD}</string>
    <key>CUKTECHRuntimePath</key><string>${RUNTIME_ROOT}</string>
    <key>CUKTECHLaunchLabel</key><string>${LAUNCH_LABEL}</string>
    <key>LSMinimumSystemVersion</key><string>14.0</string>
    <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

ACTUAL_MIN_OS="$(otool -l "$MACOS/AP01ScreenController" | awk '/minos/{print $2; exit}')"
if [[ "$ACTUAL_MIN_OS" != "14.0" ]]; then
    echo "Unexpected Mach-O deployment target: $ACTUAL_MIN_OS" >&2
    exit 1
fi

codesign --force --deep --sign - "$APP"
echo "$APP"
