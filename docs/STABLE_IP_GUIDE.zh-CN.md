# Bridge 固定 IP 与地址变更恢复指南

AP01 实时加载器保存的是一个包含**固定 IPv4 地址**的完整 URL，例如：

```text
http://192.168.31.100:8765/screen.gif
```

它不会自动寻找电脑，也不会在电脑重新获取 DHCP 地址后自动改写这个 URL。因此，
**第一次安装实时加载器前，必须先固定运行 Bridge 的电脑地址。** 这不是端口转发，
也不是公网静态 IP；需要设置的是家庭路由器里的 **DHCP 静态分配 / 地址保留**。

## 推荐做法：在路由器中保留当前地址

1. 启动 CUKTECH Screen Controller 和 Bridge。
2. 在路由器“终端设备 / DHCP 客户端”列表中找到这台电脑。以路由器显示的
   **当前 IP 和 MAC 地址**为准。
3. 打开“局域网设置 / DHCP 静态 IP 分配 / 地址保留”（不同品牌名称略有不同）。
4. 将电脑的当前 IP 绑定给当前 MAC，不要随意占用另一台设备正在使用的地址。
5. 断开并重新连接一次网络，或重启电脑，然后确认地址没有变化。
6. 只有确认固定成功后，才把该地址写入 AP01 加载器并安装。

常用只读检查命令：

```bash
# macOS：先确认默认联网接口，再读取地址
route -n get default | grep interface
ipconfig getifaddr en0
ifconfig en0 | awk '/ether/{print $2}'
```

```powershell
# Windows PowerShell
Get-NetIPConfiguration | Where-Object IPv4DefaultGateway |
  Select-Object InterfaceAlias,@{N='IPv4';E={$_.IPv4Address.IPAddress}}
Get-NetAdapter | Where-Object Status -eq Up |
  Select-Object Name,MacAddress
```

电脑可能同时存在 Wi-Fi、网线、扩展坞和 VPN。必须固定 AP01 实际能够访问、Bridge
实际监听的那个局域网接口，而不是看到的第一个地址。

## macOS 的“私有 Wi-Fi 地址”

macOS 可能向路由器使用私有 MAC。路由器中的 DHCP 保留必须绑定这个**当前网络实际
显示的 MAC**，它不一定等于电脑机身的硬件 MAC。

- 在“系统设置 → Wi-Fi → 当前网络 → 详细信息”中，将“私有 Wi-Fi 地址”保持为
  **固定**；旧版系统只有开/关时，选择一种后不要再切换。
- 不要使用会定期变化的“轮换”模式。
- 如果修改了私有地址模式，请先重新连接 Wi-Fi，再按路由器中出现的新 MAC 重建
  DHCP 保留，然后再生成固件。

## 安装前必须验证

假设准备写入加载器的地址为 `192.168.31.100`，至少验证：

```bash
curl --noproxy '*' http://192.168.31.100:8765/health
curl --noproxy '*' -I http://192.168.31.100:8765/screen.gif
```

应看到 `/health` 返回成功，`screen.gif` 返回 `HTTP 200` 和 `Content-Type: image/gif`。
安装完成并重启后，还必须在 Bridge 日志看到来自 AP01 的：

```text
GET /screen.gif 200
```

## 如果电脑 IP 后来改变

典型现象是软件本机 `/health` 正常，但日志里没有 AP01 的 `GET /screen.gif`，屏幕仍
显示旧画面、后备画面或“未连接”。按下面顺序处理：

| 处理方法 | 是否写 AP01 Flash | 何时使用 |
| --- | --- | --- |
| 在路由器中把电脑恢复为加载器原来的 IP | **不写** | 原地址空闲时，优先使用 |
| 修正 Bridge、自启、防火墙或局域网隔离 | **不写** | 地址没变但服务不可达时 |
| 固定一个新 IP，重新构建并安装新加载器 | **写一次** | 原地址已被其他设备占用或无法恢复时 |

不要把旧 IP 强行加到电脑上，除非已经从路由器设备列表和 DHCP 绑定表确认它完全
空闲。`ping` 没有回复不代表地址一定无人使用；重复 IP 会造成整台电脑局域网异常。

如果必须改用新地址：

1. 先在路由器中固定新地址；
2. 再验证新地址的 `/health` 与 `/screen.gif`；
3. 从已验证的原厂/兼容输入镜像重新生成加载器，不能把已经 Patch 的实时镜像再次
   传给 `ap01_custom_ota.py`；
4. 重新核对型号 `njcuk.enstor.ap01` 与固件 `1.0.2_0031`；
5. 安装前由用户明确确认，再进行一次 OTA Flash 写入；
6. 重启后确认新的 `GET /screen.gif 200`。

更换加载地址导致的重新安装只需要写 Flash 一次。之后换图、动态 GIF 和
Claude/Codex 额度刷新仍写入 `/tmp/.ap01q*.gif` RAM 槽位，不会随着每次刷新反复
写 Flash。

## 无法设置 DHCP 保留时

可以继续使用，但必须提前接受以下限制：

- 电脑每次重启、切换路由器、忘记并重新加入 Wi-Fi，地址都可能变化；
- 地址变化后，应先尝试把电脑恢复到加载器原地址；
- 无法恢复时，需要固定新的可用地址并重新生成、验证、安装加载器；
- 不要在地址尚未确定时反复安装固件。

推荐在首次安装前先解决 DHCP 保留。它是最稳定、最省事、也最能避免额外 Flash
写入的方案。
