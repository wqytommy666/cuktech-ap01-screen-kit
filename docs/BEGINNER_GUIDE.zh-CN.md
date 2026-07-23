# CUKTECH Screen Controller 零基础使用教程

这份教程写给完全没有编程基础的用户。正常使用时不需要写代码，也不需要每次刷固件。

> 图形软件同时提供 macOS 与 Windows 版本。Windows 的完整安装截图与故障排查见
> [Windows 使用指南](WINDOWS_GUIDE.zh-CN.md)。

## 先判断你属于哪一种情况

### 情况 A：万向屏已经显示过自定义画面或 Claude/Codex 额度

说明实时加载器已经安装完成。你只需要安装软件，之后换图片、换 GIF、刷新额度都通过
Wi-Fi 写入屏幕的临时内存，不会反复刷 Flash。

### 情况 B：万向屏还是完全原厂状态，从未显示过电脑发送的画面

需要先完成一次实时加载器安装。打开软件的“首次部署 / OTA 交接”，点击
**“无网关：一键获取部署包”**即可，不需要购买小米网关或手动准备 BIN。软件只支持
`njcuk.enstor.ap01 / 1.0.2_0031`，会先只读检查和下载验证，真正安装前再次弹窗确认。
完成一次后，日常操作就全部使用局域网和 RAM。

## 安装前准备清单

使用原生图形软件时，请提前准备好：

- Apple Silicon Mac（macOS 14+），或 Windows 10/11 x64 电脑；
- 酷态科 10 号充电站与 AP01 万向屏，屏幕保持稳定供电；
- 先在米家完成 AP01 配网并确认设备在线；
- 电脑和 AP01 连接同一个可互相访问的局域网，不能使用访客网络；
- 需要显示额度时，提前安装并登录 Claude Desktop 和官方 Codex/ChatGPT App；
- 首次安装软件时保持网络连接；
- 如果 macOS/Windows 询问是否允许接收网络连接，请允许“本地/专用网络”；
- VPN、代理或防火墙不能拦截本地局域网与 TCP `8765`；
- **首次安装加载器前必须**在路由器中为电脑固定局域网 IP；macOS 私有 Wi-Fi
  地址应保持“固定”而不是“轮换”；
- 不需要单独购买小米网关；原厂屏的一次性 FDS 上传由软件的受限共享服务完成。

> **不用准备 USB 数据线。** 本项目通过 Wi-Fi/LAN 传输画面，USB 和底座触点不参与
> 日常内容传输。详细说明见[安装前准备与联网说明](PREPARATION_CHECKLIST.zh-CN.md)。

> **为什么不能跳过固定 IP：** 万向屏保存的是电脑的具体 IP，不会自动搜索电脑。
> 如果以后 IP 改变，先在路由器中恢复旧 IP，不需要刷固件；如果旧 IP 已被占用，
> 才需要固定新 IP 并重新安装一次加载器。请先阅读
> [固定 IP 与恢复指南](STABLE_IP_GUIDE.zh-CN.md)。

### 到底哪些时候需要互联网？

- **已经改造，显示自己的图片：** 只要电脑与 AP01 的局域网正常，不需要外网；
- **显示 Claude/Codex 额度：** 电脑需要联网获取最新额度，AP01 只需能访问电脑；
- **完全原厂屏首次安装加载器：** AP01 必须在米家在线，电脑和 AP01 都要联网；
- **电脑睡眠或关机：** 额度面板约 7 分钟后显示“未连接，请连接”；自定义图片保持不变。

## 方法一：直接安装软件（最简单）

macOS 和 Windows 都可以直接安装，不要求用户写代码。

### 第 1 步：下载安装包

打开 [GitHub Releases](https://github.com/wqytommy666/cuktech-screen-controller/releases/latest)，
按电脑系统下载其中一个文件：

```text
CUKTECH-Screen-Controller-v0.4.1-macOS-arm64.zip
CUKTECH-Screen-Controller-0.4.1-Windows-x64.zip
```

### 第 2 步：运行安装程序

1. 先完整解压 ZIP；
2. macOS 双击 `Install CUKTECH Screen Controller.command`；如果被阻止，右键
   选择“打开”；
3. Windows 双击 `Install CUKTECH Screen Controller.cmd`；安装后从开始菜单打开；
4. Windows Defender 弹窗只勾选“专用网络”；
5. 等待安装完成，软件会自动打开。

macOS 若提示没有 Python 3，请安装后再运行一次。Windows Release 已自带运行环境，
不需要额外安装 Python。

### 第 2.5 步：原厂屏首次安装（已经显示过自定义画面的用户跳过）

1. 确认 AP01 在米家中在线，电脑与 AP01 使用同一家庭局域网；
2. 在路由器中把 Bridge 电脑当前 IP/MAC 设为 DHCP 静态分配，重连后确认 IP 不变；
3. 打开“首次部署 / OTA 交接”；
4. 点击“无网关：一键获取部署包”；
5. 等待 BFNP 与 SHA-256 预检通过；
6. 点击“仅下载验证（不会安装）”；
7. 验证成功后点击“确认后安装”，阅读最终提示并明确确认；
8. 等待 AP01 重启，切到电子宠物/虚拟形象页面。

Mac 使用当前已登录的米家 App 登录态；Windows 版本需要在窗口中选择仅保存在本机
的米家登录 JSON。共享服务不会收到米家密码、Token、设备 DID 或额度数据。

### 第 3 步：跟着软件里的“新手引导”检查

第一次打开软件会自动显示新手引导，也可以点击窗口右上角的“新手引导”。确认：

- 运行环境：已就绪；
- 后台服务：运行中；
- Claude：已登录（只显示自定义图片时可以忽略）；
- Codex：已登录（只显示自定义图片时可以忽略）；
- AP01 请求：最近出现过 `GET /screen.gif 200`。

### 第 4 步：选择显示内容

#### 显示 Claude / Codex 额度

点击“显示 Claude / Codex 额度”。软件每 5 分钟获取一次最新数据。第一次读取 Claude
登录状态时，macOS 可能询问是否允许访问“Claude Safe Storage”，请选择“允许”或
“始终允许”；Windows 会使用当前用户的 DPAPI 在内存中读取 Claude Desktop 登录态。

#### 显示自己的图片或 GIF

1. 选择“完整显示”“铺满裁切”或“拉伸”；
2. 点击“选择图片并推送”；
3. 选择 PNG、JPG、HEIC、WebP 或动态 GIF；
4. 等待提示“已切换为自定义画面”。

AP01 通常会在下一次轮询时更新，默认最长约 5 分钟。

## 方法二：把 GitHub 链接交给 Coding Agent

这种方法适合全新电脑、原厂屏幕首次配置或出现故障时。可以使用 Claude Code、Codex、
OpenCode、WorkBuddy 等能够读取 GitHub 并执行终端命令的软件。

把下面整段话复制给它：

```text
请使用这个公开仓库帮我配置酷态科 AP01 万向屏：
https://github.com/wqytommy666/cuktech-screen-controller

开始前先阅读仓库根目录的 AGENTS.md、README.zh-CN.md 和
skills/cuktech-ap01-screen-kit/SKILL.md。先运行只读诊断，不要直接刷固件。

我没有编程基础，请一次只告诉我一个需要人工完成的动作，并解释我应该看到什么。
请先识别当前是 macOS 还是 Windows，再检查 Python、局域网、Bridge 和 AP01
请求记录；额度模式还要检查 Claude/Codex 登录状态。Windows 不要运行 macos/
目录中的脚本，请按 docs/WINDOWS_GUIDE.zh-CN.md 操作。
首次加载器构建前，必须从路由器设备列表确认电脑当前 IP/MAC，完成 DHCP 静态地址
保留并在重连后验证。如果无法保留，先向我解释以后 IP 变化时恢复旧地址或重新安装
新地址加载器的区别，不要在地址未稳定时安装。
如果设备已经请求 GET /screen.gif，就不要进行 OTA，直接完成软件和自动启动配置。
只有确认设备仍为原厂、型号为 njcuk.enstor.ap01、固件为 1.0.2_0031 时，才准备
一次性实时加载器；真正安装前必须再次向我确认。日常图片和额度刷新只使用 /tmp RAM。

完成后请给我展示：
1. /health 的结果；
2. screen.gif 为 320×240 GIF89a；
3. 日志中的 AP01 GET /screen.gif 200；
4. 登录后自动启动已经开启。
```

Agent 会自动识别 `AGENTS.md`/`CLAUDE.md`，运行一键配置脚本，并在需要你登录、选择
图片或确认一次性安装时暂停。

## 常见问题

### 软件显示“服务未运行”

点击“重启并立即刷新”。如果仍未恢复，在“新手引导”中运行检查，或把下面这句话交给
Coding Agent：

```text
请识别当前操作系统：macOS 运行 ./macos/diagnose.sh，Windows 运行
.\scripts\diagnose-windows.ps1；修复 Bridge，但不要执行 OTA。
```

### 软件运行，但额度不更新

- 重新打开并登录 Claude Desktop、Codex/ChatGPT App；
- macOS 的 Claude 第一次读取可能需要钥匙串授权；Windows 请确认使用登录
  Claude Desktop 的同一 Windows 账户运行软件；
- 检查代理/VPN是否能访问 Claude；
- 软件会保留上一次成功画面，网络恢复后自动重试。

### 电脑重启后屏幕不更新

软件安装器会创建登录自动启动服务。电脑必须已经登录用户账户、保持开机，并与 AP01
处于同一 Wi-Fi。睡眠或关机后，额度模式约 7 分钟会明确显示“未连接，请连接”。

### 屏幕一直没有请求

确认不是访客 Wi-Fi，关闭路由器的 AP/客户端隔离，并固定电脑的局域网 IP。如果这块
屏幕从未安装实时加载器，请使用“方法二”完成一次性配置。如果软件本机正常但没有
AP01 请求，比较电脑当前 IP 与加载器原地址：优先在路由器恢复原地址，不要直接重刷；
只有原地址无法恢复时才固定新地址并重新安装一次。详见
[固定 IP 与恢复指南](STABLE_IP_GUIDE.zh-CN.md)。

### 会不会把 Flash 刷坏？

日常图片、GIF 和额度刷新只写入 `/tmp/.ap01q*.gif` RAM 槽位，不写固件分区。只有
原厂设备首次安装实时加载器时写入一次 Flash。
