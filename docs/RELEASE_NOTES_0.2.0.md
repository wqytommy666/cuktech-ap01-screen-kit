# CUKTECH Screen Controller 0.2.0

## 中文

- 新增原生 macOS SwiftUI 控制器与自定义 Logo。
- 可在 Claude/Codex 额度面板与自定义 PNG、JPG、HEIC、WebP、动态 GIF 之间切换。
- 动态 GIF 会保留动画并自动控制到 AP01 可承受的帧数与体积。
- 新增“首次部署 / OTA 交接”窗口：BFNP 与 SHA-256 预检、FDS 票据生成/导入、
  仅下载验证；不会静默安装固件。
- 支持上传账号与 AP01 所属账号分离，解决 AP01 自身没有 FDS 配置的问题。
- 增加登录自动启动 Bridge、运行状态、画面预览与局域网地址复制。
- 日常更新继续写入 `/tmp/.ap01q*.gif` RAM 槽位，不反复写 Flash。

### 安装

1. 下载并解压 `CUKTECH-Screen-Controller-v0.2.0-macOS-arm64.zip`。
2. 双击 `Install CUKTECH Screen Controller.command`。
3. 安装器会把应用放到 `~/Applications`，并创建独立 Python 运行环境。

当前包适用于 Apple Silicon 与 macOS 14 或更高版本。首次安装依赖时需要联网。

## English

- Adds the native SwiftUI **CUKTECH Screen Controller** for macOS.
- Switches between the live Claude/Codex dashboard and custom PNG, JPG, HEIC,
  WebP, or animated GIF artwork.
- Preserves GIF animation while bounding AP01 frame count and asset size.
- Adds a first-deployment window for BFNP/SHA-256 preflight, transferable FDS
  tickets, and download-only verification; it never silently installs firmware.
- Supports separate FDS-upload and AP01-owner accounts.
- Includes login auto-start, bridge health, screen preview, and LAN URL tools.
- Normal refreshes stay in RAM-backed `/tmp/.ap01q*.gif` slots rather than
  repeatedly writing Flash.

Unzip the arm64 package and double-click
`Install CUKTECH Screen Controller.command`. macOS 14 or later is required.
