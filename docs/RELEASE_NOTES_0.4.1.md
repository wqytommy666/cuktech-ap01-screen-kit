# CUKTECH Screen Controller 0.4.1

## 中文

### 不再显示含糊的旧额度

- Claude/Codex 数据仍每 5 分钟从本机官方登录态刷新；
- 在线面板的计划徽章现在带绿色状态点和最后刷新时间；
- 任何一次额度采集失败，Bridge 都会原子切换为大字“未连接 / 请连接”页面；
- Bridge 重启时不会再恢复超过有效期的旧额度截图；
- 实时 GIF 自带 7 分钟失效页面：即使电脑关机或 Bridge 完全消失，当前 GIF 也会在超时后停在“未连接，请连接”，而不是永久保留旧数字；
- 连接恢复并成功刷新后，面板会自动回到最新 Claude/Codex 额度；
- macOS 与 Windows 软件状态栏同时显示最后成功刷新时间。

日常更新仍通过局域网写入 AP01 `/tmp` RAM，不会写 Flash。

安装包：

- `CUKTECH-Screen-Controller-v0.4.1-macOS-arm64.zip`
- `CUKTECH-Screen-Controller-0.4.1-Windows-x64.zip`

## English

Version 0.4.1 makes quota freshness explicit. Live cards include a green state
dot and the latest successful refresh time. Failed collection atomically swaps
the served asset to a large disconnected screen. Live GIFs also self-expire to
that final status frame after seven minutes, so a powered-off computer cannot
leave an apparently current quota card on screen forever. A successful refresh
automatically restores the live dashboard. Daily updates remain LAN-only and
RAM-backed.
