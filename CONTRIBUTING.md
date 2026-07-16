# Contributing / 参与贡献

## English

1. Keep the AP01 screen contract: 320×240, GIF89a, two or more frames.
2. Keep generated firmware, account data, local IPs, device IDs, and artifacts
   out of commits.
3. Add or update a focused test for renderer, converter, or patcher changes.
4. Run `python -m unittest -v test_quota_dashboard.py` before opening a PR.
5. For a firmware offset change, include the firmware version, exact validation
   evidence, hook readback, recovery CRC, and an AP01 request trace.

## 简体中文

1. 保持 AP01 屏幕协议：320×240、GIF89a、至少两帧。
2. 不提交生成固件、账号数据、局域网 IP、设备 ID 与运行产物。
3. 修改渲染器、转换器或 Patch 时，补充对应的聚焦测试。
4. 提交 PR 前运行 `python -m unittest -v test_quota_dashboard.py`。
5. 修改固件偏移时，附上固件版本、验证证据、Hook 回读、Recovery CRC 与
   AP01 请求日志。
