#!/bin/zsh
set -euo pipefail

HERE="${0:A:h}"
ROOT="${HERE:h}"
VERSION="${1:-0.4.1}"
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
  ap01_fds_relay_client.py \
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
cp "$HERE/diagnose.sh" "$RUNTIME/macos/"
cp "$HERE/store_mi_home_keychain.py" "$RUNTIME/macos/"
chmod +x "$RUNTIME/macos/"*.sh
echo "quota" > "$RUNTIME/artifacts/ap01-mode"

CUKTECH_PORTABLE=1 CUKTECH_VERSION="$VERSION" CUKTECH_BUILD="${CUKTECH_BUILD:-7}" \
  "$HERE/build-app.sh" >/dev/null
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
chmod 700 "$SUPPORT" "$RUNTIME" "$RUNTIME/artifacts" 2>/dev/null || true

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
    echo "当前安装包只支持 Apple Silicon Mac（M 系列，包括 2024/2025/2026 款）。"
    read -k 1 "?按任意键退出…"
    exit 1
fi
MAC_MAJOR="$(sw_vers -productVersion | cut -d. -f1)"
if (( MAC_MAJOR < 14 )); then
    echo "当前安装包需要 macOS 14 或更高版本。"
    read -k 1 "?按任意键退出…"
    exit 1
fi

PYTHON=""
for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if [[ -x "$candidate" ]] && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 9))' 2>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done
if [[ -z "$PYTHON" ]]; then
    echo "未找到 Python 3.9 或更高版本。"
    echo "即将打开 Python 官方下载页面；安装后重新运行本安装程序。"
    if [[ "${CUKTECH_SKIP_OPEN:-0}" != "1" ]]; then
        open "https://www.python.org/downloads/macos/"
    fi
    read -k 1 "?按任意键退出…"
    exit 1
fi

if [[ ! -x "$RUNTIME/.venv/bin/python" ]]; then
    echo "[1/4] 创建独立运行环境…"
    "$PYTHON" -m venv "$RUNTIME/.venv"
fi
echo "[2/4] 安装图片与网络组件…"
if [[ "${CUKTECH_SKIP_DEPENDENCIES:-0}" != "1" ]]; then
    "$RUNTIME/.venv/bin/python" -m pip install --disable-pip-version-check -r "$RUNTIME/requirements.txt"
fi
"$RUNTIME/.venv/bin/python" -c 'import PIL, requests, cryptography'

if "$RUNTIME/.venv/bin/python" "$RUNTIME/macos/store_mi_home_keychain.py" \
  --service com.wqytommy.CUKTECHScreenController.mi-home-owner \
  --account owner; then
    echo "      米家首次部署登录态已保存到当前用户钥匙串"
else
    echo "[提示] 暂未找到米家登录态；日常换图不受影响。首次部署前请登录米家并重新运行安装程序。"
fi

echo "[3/4] 安装应用…"
rm -rf "$APP_TARGET"
/usr/bin/ditto "$HERE/CUKTECH Screen Controller.app" "$APP_TARGET"

echo "[4/4] 安装登录自动启动服务…"
if [[ "${CUKTECH_SKIP_LAUNCH_AGENT:-0}" != "1" ]]; then
    "$RUNTIME/macos/install-launch-agent.sh"
else
    echo "已跳过 LaunchAgent（测试模式）"
fi

echo ""
echo "安装完成：$APP_TARGET"
echo "第一次打开后，请跟随软件右上角的“新手引导”完成检查。"
if [[ "${CUKTECH_SKIP_OPEN:-0}" != "1" ]]; then
    open "$APP_TARGET"
fi
sleep 2
INSTALL

chmod +x "$STAGE/Install CUKTECH Screen Controller.command"
cat > "$STAGE/先读我.txt" <<TXT
CUKTECH Screen Controller $VERSION

1. 双击“Install CUKTECH Screen Controller.command”。
2. 若 macOS 阻止打开，请右键安装程序并选择“打开”。
3. 首次安装会下载 Python 依赖，需要联网。
4. 安装完成后，应用位于 ~/Applications。
5. 第一次打开会自动显示“新手引导”。
6. Claude Desktop 与官方 Codex/ChatGPT App 需提前登录。
7. Mac 与 AP01 必须处于同一个非访客、未隔离局域网。
8. AP01 需要先在米家完成配网并显示在线，首次部署期间保持稳定供电。
9. 日常画面通过 Wi-Fi/LAN 传输，不需要 USB 数据线。

完整零基础教程：
https://github.com/wqytommy666/cuktech-screen-controller/blob/main/docs/BEGINNER_GUIDE.zh-CN.md

安装前准备与联网说明：
https://github.com/wqytommy666/cuktech-screen-controller/blob/main/docs/PREPARATION_CHECKLIST.zh-CN.md

日常画面刷新只写 AP01 的 /tmp RAM 槽位，不会反复刷写 Flash。
TXT

/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$STAGE" "$ZIP"
(
    cd "$ROOT/dist"
    /usr/bin/shasum -a 256 "${ZIP:t}" > "${ZIP:t}.sha256"
)
echo "$ZIP"
