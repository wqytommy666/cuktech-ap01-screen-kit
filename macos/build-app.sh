#!/bin/zsh
set -euo pipefail

HERE="${0:A:h}"
ROOT="${HERE:h}"
RUNTIME_ROOT="${CUKTECH_PROJECT_ROOT:-$ROOT}"
if [[ "${CUKTECH_PORTABLE:-0}" == "1" ]]; then
    RUNTIME_ROOT=""
fi
LAUNCH_LABEL="${CUKTECH_LAUNCH_LABEL:-io.github.wqytommy666.cuktech-screen-controller.bridge}"
ICON_PYTHON="${CUKTECH_PYTHON:-$ROOT/.venv/bin/python}"
APP="$ROOT/dist/CUKTECH Screen Controller.app"
CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
MODULE_CACHE="$ROOT/.build/ModuleCache"

mkdir -p "$MACOS" "$RESOURCES" "$MODULE_CACHE"
xcrun swiftc \
    -parse-as-library \
    -O \
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
    <key>CFBundleShortVersionString</key><string>0.2.0</string>
    <key>CFBundleVersion</key><string>2</string>
    <key>CUKTECHRuntimePath</key><string>${RUNTIME_ROOT}</string>
    <key>CUKTECHLaunchLabel</key><string>${LAUNCH_LABEL}</string>
    <key>LSMinimumSystemVersion</key><string>14.0</string>
    <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

codesign --force --deep --sign - "$APP"
echo "$APP"
