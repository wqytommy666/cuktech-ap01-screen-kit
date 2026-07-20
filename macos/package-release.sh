#!/bin/zsh
set -euo pipefail

HERE="${0:A:h}"
ROOT="${HERE:h}"
VERSION="${1:-0.2.0}"
STAGE="$ROOT/dist/CUKTECH-Screen-Controller-$VERSION"
RUNTIME="$STAGE/Runtime"
ZIP="$ROOT/dist/CUKTECH-Screen-Controller-v$VERSION-macOS-arm64.zip"

rm -rf "$STAGE" "$ZIP"
mkdir -p "$RUNTIME/reference" "$RUNTIME/macos" "$RUNTIME/artifacts"

for file in \
  ap01_prepare_screen.py \
  ap01_screen_bridge.py \
  ap01_wifi_bridge.py \
  quota_dashboard.py \
  ap01_custom_ota.py \
  ap01_install_firmware.py \
  mi_cloud.py \
  patch_asset.py \
  requirements.txt; do
    if [[ -f "$ROOT/$file" ]]; then
        cp "$ROOT/$file" "$RUNTIME/$file"
    fi
done

if [[ ! -f "$RUNTIME/requirements.txt" ]]; then
    cat > "$RUNTIME/requirements.txt" <<'REQ'
Pillow>=10.0
requests>=2.31
cryptography>=42.0
REQ
fi

cp -R "$ROOT/reference/provider-icons" "$RUNTIME/reference/provider-icons"
cp "$HERE/ap01-bridge-runner.sh" "$RUNTIME/macos/"
cp "$HERE/install-launch-agent.sh" "$RUNTIME/macos/"
cp "$HERE/uninstall-launch-agent.sh" "$RUNTIME/macos/"
chmod +x "$RUNTIME/macos/"*.sh
echo "quota" > "$RUNTIME/artifacts/ap01-mode"

CUKTECH_PORTABLE=1 "$HERE/build-app.sh" >/dev/null
/usr/bin/ditto "$ROOT/dist/CUKTECH Screen Controller.app" "$STAGE/CUKTECH Screen Controller.app"

cat > "$STAGE/Install CUKTECH Screen Controller.command" <<'INSTALL'
#!/bin/zsh
set -euo pipefail

HERE="${0:A:h}"
SOURCE_RUNTIME="$HERE/Runtime"
SUPPORT="$HOME/Library/Application Support/CUKTECH Screen Controller"
RUNTIME="$SUPPORT/runtime"
APP_TARGET="$HOME/Applications/CUKTECH Screen Controller.app"

echo "CUKTECH Screen Controller 安装程序"
echo "==================================="
mkdir -p "$RUNTIME" "$HOME/Applications"
/usr/bin/ditto "$SOURCE_RUNTIME" "$RUNTIME"
chmod +x "$RUNTIME/macos/"*.sh

PYTHON=""
for candidate in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [[ -x "$candidate" ]]; then
        PYTHON="$candidate"
        break
    fi
done
if [[ -z "$PYTHON" ]]; then
    echo "未找到 Python 3。请先安装 Xcode Command Line Tools 或 Python 3。"
    read -k 1 "?按任意键退出…"
    exit 1
fi

if [[ ! -x "$RUNTIME/.venv/bin/python" ]]; then
    echo "[1/4] 创建独立运行环境…"
    "$PYTHON" -m venv "$RUNTIME/.venv"
fi
echo "[2/4] 安装图片与网络组件…"
"$RUNTIME/.venv/bin/python" -m pip install --disable-pip-version-check -r "$RUNTIME/requirements.txt"

echo "[3/4] 安装应用…"
rm -rf "$APP_TARGET"
/usr/bin/ditto "$HERE/CUKTECH Screen Controller.app" "$APP_TARGET"

echo "[4/4] 安装登录自动启动服务…"
"$RUNTIME/macos/install-launch-agent.sh"

echo ""
echo "安装完成：$APP_TARGET"
open "$APP_TARGET"
sleep 2
INSTALL

chmod +x "$STAGE/Install CUKTECH Screen Controller.command"
cat > "$STAGE/先读我.txt" <<'TXT'
CUKTECH Screen Controller 0.2.0

1. 双击“Install CUKTECH Screen Controller.command”。
2. 首次安装会下载 Python 依赖，需要联网。
3. 安装完成后，应用位于 ~/Applications。
4. Claude Desktop 与官方 Codex App 需提前登录。
5. Mac 与 AP01 必须处于同一个未隔离的 Wi-Fi。

日常画面刷新只写 AP01 的 /tmp RAM 槽位，不会反复刷写 Flash。
TXT

/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$STAGE" "$ZIP"
echo "$ZIP"
