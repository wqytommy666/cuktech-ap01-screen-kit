# AP01 无外置网关时的 FDS 上传与 `download-only` 解决方案

> 本文是给执行安装任务的 Agent 使用的操作说明。目标设备为酷态科 AP01，
> model `njcuk.enstor.ap01`，固件 `1.0.2_0031`。当前只验证 AP01 能完整
> 下载并校验 `screen-realtime.bin`，**不执行安装**。

## 1. 已知状态

- `screen-realtime.bin` 已生成并完成本地结构校验。
- 文件头应为 `BFNP`。
- AP01 已加入执行者的米家账号，且当前在线。
- AP01 账号中没有独立的 `lumi.gateway.*` 或 `xiaomi.gateway.*` 网关。
- 使用 AP01 自己的 DID/model 请求 `/home/genpresignedurl` 返回：

```text
code: -6
message: invalid config for fds
```

## 2. 根因与必须遵守的结论

`/home/genpresignedurl` 会根据传入的设备 model 查询小米服务端 FDS 配置。
`njcuk.enstor.ap01` 没有该配置，因此 AP01 DID/model 不能用于申请上传地址。
这不是 BIN、MD5、Recovery CRC、网络或 Loader Patch 的故障。

上传和下载使用的是两个不同身份：

| 阶段 | 身份 |
| --- | --- |
| 申请 FDS URL、上传 BIN | 真实具备 FDS 配置的 `lumi.gateway.*` / `xiaomi.gateway.*` DID/model |
| 发送 `miIO.ota` | 最终目标 AP01 的 DID |

不存在可手工填写的 AP01 bucket、隐藏 model、通用 DID 或固定 `obj_name`。
不要继续拿 AP01 DID/model 重试 `/home/genpresignedurl`。

## 3. 推荐方案：上传账号与 AP01 账号分离

让一个可信的、米家账号中包含 FDS 网关的执行环境负责上传。签名 URL 自带
下载授权，可交给另一个米家账号中的 AP01 使用。

两端必须使用**逐字节完全相同**的 `screen-realtime.bin`。不得在上传后再次
构建、重新打补丁或替换资源。

### 3.1 两端先更新仓库

```bash
git clone https://github.com/wqytommy666/cuktech-screen-controller.git
cd cuktech-screen-controller
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

已有仓库时：

```bash
git pull --ff-only
.venv/bin/python ap01_install_firmware.py --help
```

帮助中必须出现以下参数：

```text
--upload-only
--download-only
--ota-url
--ota-url-file
--url-output
--fds-did
--fds-model
```

### 3.2 校验双方 BIN 一致

分别在两个环境中执行：

```bash
shasum -a 256 ./screen-realtime.bin
```

两个 SHA-256 必须完全一致。再确认文件头：

```bash
xxd -l 4 ./screen-realtime.bin
```

预期 ASCII 为：

```text
BFNP
```

### 3.3 A 端：含 FDS 网关的账号只负责上传

在已登录含网关米家账号的 Mac 上执行：

```bash
.venv/bin/python ap01_install_firmware.py \
  ./screen-realtime.bin \
  --upload-only \
  --url-output /tmp/ap01-ota-url.txt
```

如果自动发现了多个网关，或需要显式选择，使用该账号真实拥有且确实具备
FDS 配置的身份：

```bash
.venv/bin/python ap01_install_firmware.py \
  ./screen-realtime.bin \
  --upload-only \
  --fds-did '真实网关DID' \
  --fds-model 'lumi.gateway.真实型号' \
  --url-output /tmp/ap01-ota-url.txt
```

这里的 `--fds-did` 只用于申请上传地址，不是最终 AP01 DID。不能填写
`njcuk.enstor.ap01`，也不能通过伪造 model 获得服务端配置。

成功后 `/tmp/ap01-ota-url.txt` 应包含一条短时有效 URL，通常使用以下域名：

```text
https://iot-ota-cdn.io.mi.com/...
```

将该文本文件立即发送给 B 端。不要把签名 URL 提交进 Git、Issue 或日志。

### 3.4 B 端：AP01 所属账号只执行下载验证

将收到的 URL 文件保存为 `./ap01-ota-url.txt`，然后执行：

```bash
.venv/bin/python ap01_install_firmware.py \
  ./screen-realtime.bin \
  --download-only \
  --ota-url-file ./ap01-ota-url.txt \
  --timeout 360
```

禁止加入 `--install`。上述流程会：

1. 从 URL 回读前四字节并确认是 `BFNP`；
2. 从 B 端米家账号中自动寻找 `njcuk.enstor.ap01`；
3. 计算 B 端本地 BIN 的 MD5 和文件长度；
4. 向 AP01 发送 `miIO.ota`，其中 `proc=dnld`；
5. 轮询 `miIO.get_ota_state` 和 `miIO.get_ota_progress`；
6. 在下载及校验完成后退出，不发送安装指令。

成功输出应接近：

```text
已验证外部 OTA URL 的 BFNP 文件头；跳过 FDS 上传
设备已接受 OTA 下载测试；本次不安装、不切换启动分区…
[  0s] state=downloading progress=...
...
state=downloaded progress=100
下载校验已完成；镜像尚未安装
```

## 4. Agent 故障分流

### `code=-6 / invalid config for fds`

仍在使用 AP01 DID/model，或 A 端选择的所谓网关没有 FDS 服务端配置。
更换真实可用的上传账号/网关；不要修改 bucket。

### `账号中未找到可用于 Xiaomi FDS 上传的网关`

当前执行的是上传步骤，但登录的是只有 AP01 的账号。切换到 A 端账号，或者
跳过上传，使用 `--ota-url-file`。

### URL 回读为 `403`、签名错误或已过期

签名 URL 已失效。A 端重新执行 `--upload-only`，生成新文件后立即交给 B 端。

### `不是 AP01 BFNP 镜像`

URL 指向了错误文件、发生了网页跳转，或上传的不是最终 BIN。不要继续下发。

### `njcuk.enstor.ap01 was not found`

B 端本机米家登录的账号不包含目标 AP01，或区域/账号不一致。修正米家登录
状态后重新执行，不要把 A 端网关账号用于 AP01 下发。

### `AP01 未接受 OTA`

确认 AP01 在线，且 B 端账号确实拥有目标设备。记录完整 RPC `code`，不要
改为 `--install` 重试。

### `progress=101`

读取脚本返回的 `ota_error`。常见原因包括 URL 过期、TLS/CDN 不兼容、MD5
不一致或文件长度不一致。先比较双方 SHA-256，再重新生成签名 URL。

## 5. 不可采用的替代做法

- 不要用 AP01 DID/model 反复调用 `/home/genpresignedurl`。
- 不要猜测或硬编码 FDS bucket、`obj_name`、签名参数。
- 不要把普通局域网 HTTP URL直接作为 AP01 OTA URL；固件 OTA 客户端与
  实时 GIF Loader 是两条不同链路。
- 不要默认 GitHub Release、网盘、任意 S3 HTTPS 都与 AP01 的 mbedTLS
  兼容；重定向、证书链和 TLS 配置都可能失败。
- 不要在本任务中使用 `--install`。
- 不要把已经注入实时 Loader 的 BIN 再传给 `ap01_custom_ota.py` 重建。

## 6. 本任务的完成标准

- URL 回读确认 `BFNP`；
- AP01 接受 `miIO.ota` 下载请求；
- OTA 状态达到 `downloaded` 或进度达到 `100`；
- 日志输出“下载校验已完成；镜像尚未安装”；
- AP01 未重启，未切换启动分区，未执行安装。

达到以上状态后停止，保存两端 SHA-256、下载验证日志和生成时间。实际安装
应作为另一个明确授权的步骤单独执行。
