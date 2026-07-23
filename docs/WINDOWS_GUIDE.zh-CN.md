# Windows 使用指南

CUKTECH Screen Controller 现已提供 **Windows 10/11 x64 图形软件**。它和
macOS 版使用同一套 AP01 Bridge 与画面格式，可以直接切换 Claude/Codex 额度、
推送图片或动态 GIF、查看实时预览、设置登录自动启动，并完成首次 OTA 票据交接。

![Windows 主界面](images/windows-controller-main.png)

## 功能支持

| 功能 | Windows 10/11 x64 |
| --- | --- |
| 原生风格图形控制器 | ✅ |
| PNG/JPG/WebP/BMP/TIFF/动态 GIF | ✅ |
| `contain` / `cover` / `stretch` | ✅ |
| Claude Desktop 5 小时、本周、Fable 5 | ✅，读取当前 Windows 用户的本地登录态 |
| Codex 5 小时、本周 | ✅，通过官方 Codex `app-server` |
| 每 5 分钟自动刷新与 AP01 实时预览 | ✅ |
| 登录 Windows 后自动运行 Bridge | ✅ |
| 新手检查、日志、`/health` | ✅ |
| BFNP 校验、FDS 票据、`download-only` | ✅ |
| macOS SwiftUI 安装包和 LaunchAgent | 不适用；Windows 使用本页软件与启动项 |

## 方法一：安装 Windows 软件（推荐）

1. 打开 [GitHub Releases](https://github.com/wqytommy666/cuktech-screen-controller/releases/latest)；
2. 下载 **`CUKTECH-Screen-Controller-0.4.1-Windows-x64.zip`**；
3. 右键 ZIP，选择“全部解压”。不要在压缩包预览窗口里直接运行；
4. 双击 **`Install CUKTECH Screen Controller.cmd`**；
5. 安装后从开始菜单打开 **CUKTECH Screen Controller**；
6. Windows Defender 首次询问时，只允许它访问“专用网络”。

软件安装在：

```text
%LOCALAPPDATA%\Programs\CUKTECH Screen Controller
```

画面、模式、日志与 PID 保存在：

```text
%LOCALAPPDATA%\CUKTECH Screen Controller
```

更新软件时重新运行新版安装器即可，用户画面和日志不会被删除。卸载脚本默认也会
保留这些数据；如要同时删除，可用 PowerShell 执行：

```powershell
.\Uninstall-CUKTECHScreenController.ps1 -RemoveUserData
```

## 第一次打开

点击右上角“新手引导”，按顺序确认：

1. AP01 稳定供电，已在米家完成配网并显示在线；
2. Windows 电脑与 AP01 在同一个非访客、未开启 AP/客户端隔离的局域网；
3. 额度模式已登录 Claude Desktop 和官方 Codex/ChatGPT App；
4. Bridge 状态为“服务运行中”；
5. AP01 下一次轮询后，日志出现 `GET /screen.gif 200`。

![Windows 新手引导](images/windows-controller-guide.png)

AP01 日常通过 **Wi-Fi/LAN** 获取画面，不使用 USB，也不通过底座五个触点传图。
电脑可以接网线，只要 AP01 能访问电脑的局域网 IPv4 与 TCP `8765`。

## 显示 Claude / Codex 额度

1. 在当前 Windows 用户下登录 Claude Desktop；
2. 登录官方 Codex App，或安装并登录 Codex CLI；
3. 打开控制器，点击“显示 Claude / Codex 额度”；
4. 首次读取后等待 AP01 的下一次轮询。

软件会在本机内存中读取 Claude 的 Electron/Chromium Cookie，并通过 DPAPI 解密；
Codex 使用官方本地 `app-server`。Session、Cookie 和 Token 不会写入额度图片或
API JSON。默认每 **300 秒（5 分钟）**刷新一次。

若 Codex 不在常见路径，可在启动软件前设置：

```powershell
$env:CUKTECH_CODEX_BIN = "C:\path\to\codex.exe"
```

## 推送自定义图片或 GIF

1. 选择“完整显示”“铺满裁切”或“拉伸”；
2. 点击“选择图片并推送”；
3. 选择 PNG、JPG、WebP、BMP、TIFF 或 GIF；
4. 软件会生成通过校验的 `320×240`、GIF89a、至少双帧画面并重启 Bridge；
5. AP01 会在下一次轮询时显示新内容。

输出文件位于：

```text
%LOCALAPPDATA%\CUKTECH Screen Controller\artifacts\custom-screen.gif
```

## 局域网与防火墙

浏览器打开以下地址进行本机验证：

```text
http://127.0.0.1:8765/health
http://127.0.0.1:8765/screen.gif
```

然后用界面显示的局域网地址测试，例如：

```text
http://192.168.1.20:8765/screen.gif
```

若本机可访问而 AP01 没有请求：

- 将当前网络设为“专用网络”；
- 在 Defender 防火墙中允许 `CUKTECHRuntime.exe` 的专用网络访问；
- 关闭 VPN 的“阻止本地网络”选项；
- 不要使用访客 Wi-Fi，关闭 AP/客户端隔离；
- 建议在路由器中为电脑保留固定 DHCP 地址；
- 已换过电脑/IP 的 Loader 可能仍指向旧地址，需要重新构建一次 Loader URL，
  但不要因为普通画面没刷新而盲目重复 OTA。

## 首次部署 / OTA 交接

![Windows OTA 窗口](images/windows-controller-ota.png)

已经能显示自定义画面的 AP01 **不需要再次 OTA**。完全原厂的 AP01 需要一次性
安装与 `njcuk.enstor.ap01`、`1.0.2_0031` 完全匹配的实时 Loader。

Windows 版可完成：

- 点击“无网关：一键获取部署包”，不需要用户购买网关或准备 BIN；
- 检查 `screen-realtime.bin` 的 BFNP 文件头和 SHA-256；
- 导入别人生成的短时 FDS URL；
- 使用具备 FDS 配置的网关账号生成票据；
- 对 AP01 执行 `download-only` 下载与 MD5 验证；
- 下载验证成功后，经过单独确认完成一次性安装；
- 自动在日志中隐藏签名 URL 的查询参数。

Windows 没有 macOS 米家 App 的 plist。需要云端操作时，软件只在本次进程中读取
你选择的本机 JSON，格式见压缩包里的 `mi-credentials.example.json`：

```json
{
  "userId": "YOUR_XIAOMI_USER_ID",
  "passToken": "YOUR_LOCAL_PASS_TOKEN",
  "deviceId": "OPTIONAL_DEVICE_ID"
}
```

不要把该文件提交到 GitHub、截图或发送给他人。AP01 本身不能申请 FDS 上传地址，
但普通用户可直接使用受限共享服务。共享服务只接收私有 Bridge 地址和刷新间隔，
不会接收该 JSON、设备 DID 或用户上传的 BIN。完整说明见
[共享 FDS 服务](FDS_RELAY_OPERATOR.zh-CN.md)。

## 方法二：从源码运行

已安装 Python 3.9+ 时，在 PowerShell 中执行：

```powershell
git clone https://github.com/wqytommy666/cuktech-screen-controller.git
cd cuktech-screen-controller
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-windows.ps1 -App
```

以后可手工启动：

```powershell
.\.venv\Scripts\pythonw.exe .\windows\AP01ScreenController.py
```

只需命令行 Bridge 时，不加 `-App`：

```powershell
.\scripts\setup-windows.ps1 -InputImage "C:\Pictures\screen.png"
.\.venv\Scripts\python.exe -u ap01_screen_bridge.py artifacts\custom-screen.gif --port 8765
```

执行只读诊断：

```powershell
.\scripts\diagnose-windows.ps1
```

## Flash 写入说明

首次 Loader 安装会写一次固件 Flash。之后的图片、GIF 和额度刷新仅轮换 AP01 的：

```text
/tmp/.ap01q0.gif
/tmp/.ap01q1.gif
/tmp/.ap01q2.gif
```

这些路径位于 RAM。每 5 分钟刷新额度不会反复擦写固件或资源分区，也不会把
Flash“刷烂”。电脑睡眠或关机后，额度模式约 7 分钟会显示“未连接，请连接”；
电脑恢复后自动继续刷新。

## 系统要求与限制

- Windows 10 或 Windows 11，64 位 x86（x64）；
- 当前 Release 不支持 Windows on ARM 原生运行；
- AP01 型号 `njcuk.enstor.ap01`；一次性 Loader 仅适配固件 `1.0.2_0031`；
- 实时刷新要求电脑保持开机、当前用户已登录、Bridge 正在运行；
- 软件不是米家官方产品，日常画面链路是本地 LAN HTTP。
