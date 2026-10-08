# SpacemiT AI Gateway

SpacemiT AI Gateway — ASR / TTS / VAD / Vision / LLM / Embed / Rerank 统一 HTTP + WebSocket API 服务，运行于 K3 RISC-V 嵌入式设备。

## 安装

生产部署用 `.deb` 包一键完成 apt 依赖、Python 环境、systemd 服务注册启动，无需手动操作。源码开发或调试请参考 [软件调试](#软件调试) 章节。


`spacemit-ai-gateway` 已发布到 SpacemiT 内部 apt 源。包内带完整的安装钩子：apt 系统依赖随 `debian/control` 的 `Depends` 字段自动解析；postinst 脚本会在 `/opt/spacemit-ai-gateway/venv` 创建虚拟环境，并按 `/opt/spacemit-ai-gateway/requirements-runtime.txt` 从 SpacemiT GitLab PyPI 拉取锁定版本的 `spacemit-asr/tts/vad/audio/vision` 与 `spacemit-ai-gateway` wheel；systemd 单元 `spacemit-ai-gateway.service` 由 `dh_installsystemd` 自动注册并启动。
`.deb` 同时安装运行配置到 `/opt/spacemit-ai-gateway/configs/`，安装模型清单 schema 到 `/opt/spacemit-ai-gateway/schema/`。

```bash
sudo apt update
sudo apt install spacemit-ai-gateway
```

安装过程会从 SpacemiT 内网 PyPI 按 `requirements-runtime.txt` 中锁定的 wheel 版本拉取多个 wheel；若内部 PyPI 缺少任一版本，安装会失败以避免混合运行时。首次执行可能耗时几分钟，请耐心等待。完成后查看运行状态与日志：

```bash
systemctl status spacemit-ai-gateway
journalctl -u spacemit-ai-gateway -f
```

安装完成后，两个 systemd 服务同时启动：

| 服务 | 端口 | 说明 |
|------|------|------|
| `spacemit-ai-gateway` | 18790 | backend HTTP/WebSocket API |
| `spacemit-ai-gateway-frontend` | 8326 | 前端 console 静态站点（`python3 -m http.server`） |

前端访问入口：`http://<设备 IP>:8326/`（landing 页）或 `http://<设备 IP>:8326/console/`（控制台）。前端通过浏览器内 `@babel/standalone` 现编译 JSX，无需 Node/构建步骤。

卸载：`sudo apt remove spacemit-ai-gateway` 会停止两个服务、删除 systemd unit、前端静态资源和 `/opt/spacemit-ai-gateway/venv`。如果 `/opt/spacemit-ai-gateway/` 下还有遗留目录，用 `sudo apt purge spacemit-ai-gateway` 强制清理。

## 软件调试

源码开发或调试运行使用以下流程；生产部署直接用 [.deb 安装](#安装) 即可，无需手动跑这些步骤。


### 系统依赖

```bash
sudo apt install opencv-spacemit espeak-ng llama.cpp-tools-spacemit \
    python3-spacemit-ort spacemit-onnxruntime
```

| 包名 | 用途 |
|------|------|
| `opencv-spacemit` | Vision 图像处理 |
| `espeak-ng` | TTS 音素前端 |
| `llama.cpp-tools-spacemit` | LLM 本地推理（llama-server） |
| `python3-spacemit-ort` | ONNX Runtime Python 绑定 |
| `spacemit-onnxruntime` | SpaceMIT EP 加速推理 |

### Python 依赖

`spacemit-ai-gateway` wheel 和 `spacemit-asr`、`spacemit-tts`、
`spacemit-vad`、`spacemit-audio`、`spacemit-vision` 等 Python 包统一发布到 SpacemiT GitLab PyPI：

- 包页面：https://git.spacemit.com/archive/pypi/-/packages
- pip simple index：`https://git.spacemit.com/api/v4/projects/33/packages/pypi/simple`

从 SpacemiT 包仓库安装 model_zoo wheel：

```bash
python -m pip install \
    --index-url https://git.spacemit.com/api/v4/projects/33/packages/pypi/simple \
    spacemit-asr spacemit-tts spacemit-vad spacemit-audio spacemit-vision
```

安装 `spacemit-ai-gateway` wheel 时只会自动拉取这些 SpacemiT Python 依赖，不会安装 apt 系统包。运行前必须先安装上一节列出的系统依赖：

- `opencv-spacemit`
- `espeak-ng`
- `llama.cpp-tools-spacemit`
- `python3-spacemit-ort`
- `spacemit-onnxruntime`

缺少这些系统包时，对应域会启动失败或在导入/推理时失败。例如未安装 `opencv-spacemit` 时，所有依赖 `cv2` 的代码路径都无法运行；`tests/unit/` 内不触发真实后端的纯单元测试不受影响。

如需在 SDK 环境中本地编译 model_zoo 依赖：

```bash
source build/envsetup.sh
cd components/model_zoo/asr && mm
cd components/model_zoo/tts && mm
cd components/model_zoo/vad && mm
```

### 安装 wheel

```bash
python -m pip install spacemit-ai-gateway \
    --prefer-binary \
    --index-url https://git.spacemit.com/api/v4/projects/33/packages/pypi/simple \
    --extra-index-url https://mirrors.aliyun.com/pypi/simple/
```

从源码构建 wheel：

```bash
python -m build --wheel
python -m pip install dist/spacemit_ai_gateway-*.whl
```

### 启动

```bash
# 命令行入口
spacemit-ai-gateway

# 或直接使用 uvicorn
uvicorn spacemit_ai_gateway.app.main:app --host 0.0.0.0 --port 18790
```

### 验证

```bash
curl -s localhost:18790/healthz | jq .
```

## 配置

配置文件位于 `configs/`。源码运行默认使用 wheel 包内置配置；`.deb` 安装后 systemd 服务显式读取
`/opt/spacemit-ai-gateway/configs/base.yaml`，便于设备侧直接查看和调整运行配置。

| 文件 | 说明 |
|------|------|
| `base.yaml` | 默认配置（ASR/TTS/VAD 参数、端口、鉴权等） |
| `dev.yaml` | 开发环境覆盖 |
| `vision/` | 视觉模型 YAML（`model_id` 与文件名一致）：YOLOv8/YOLOv11 的 n/s/m 及 `-pose`/`-seg` 变体、YOLOv5 人脸/手势、ResNet、情绪、ArcFace、ByteTrack、OC-SORT 等 |

模型清单 schema 位于 `schema/`，供外部工具读取；`.deb` 安装路径为
`/opt/spacemit-ai-gateway/schema/`。
ASR/TTS 默认只预载 `sensevoice` 和 `matcha_zh_en`，避免启动时同时加载多个语音模型占用内存。

默认使用 wheel 包内置配置，和启动所在目录无关。需要覆盖配置时，通过环境变量显式指定配置文件：

```bash
SPACEMIT_AI_GATEWAY_CONFIG=configs/dev.yaml spacemit-ai-gateway
```

支持环境变量覆盖任意配置项（前缀 `SPACEMIT_AI_GATEWAY_`，嵌套用 `__` 分隔）：

```bash
SPACEMIT_AI_GATEWAY_ASR__BACKEND=qwen3-asr spacemit-ai-gateway
```

### 模型缓存与自动加载

模型文件统一放在 `~/.cache/models/<domain>/`，和 ASR/TTS/VAD/Vision 的缓存布局保持一致：

| 域 | 模型目录 |
|----|----------|
| ASR | `~/.cache/models/asr/sensevoice` |
| TTS | `~/.cache/models/tts/matcha-tts` |
| VAD | `~/.cache/models/vad` |
| LLM | `~/.cache/models/llm` |
| Embed | `~/.cache/models/embed` |
| Rerank | `~/.cache/models/rerank` |

Gateway 自己的 SQLite 注册表放在 `~/.cache/spacemit-ai-gateway/<domain>/db.sqlite`，不存放模型文件。

LLM / Embed / Rerank 的 `backend` 配置非空时，服务启动会尝试自动下载并加载默认模型。K3 8GB 内存环境不建议同时自动加载多个 GGUF 模型；如果只需要运行管理接口或按需加载模型，可关闭默认自动加载：

```yaml
llm:
  backend: null
embed:
  backend: null
rerank:
  backend: null
```

按需加载时再调用对应域的 `POST /models/load` 或 `POST /models/switch`。

### 模型下载

8 个域都提供同一组下载接口（路径相对各域前缀，如 `/v1/llm`、`/v1/asr`、`/v1/vision`）：

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/models/{id}/download` | 开始下载（后台进行，立即返回） |
| GET | `/models/{id}/download` | 查询状态、进度和失败原因 |
| DELETE | `/models/{id}/download` | 取消下载，并删除已下载部分 |

ASR/TTS/VAD/Vision 的 `GET /models` 返回 `downloaded` 字段；LLM/Embed/Rerank/VLM 的 `GET /models` 返回 `status`（`available`/`downloading`/`downloaded`/`error`/...）。
ASR 的 `qwen3-asr` 不由 gateway 下载（返回 `download_not_supported`）。

`GET .../download` 返回字段：`status`、`progress`（0–1）、`downloaded_bytes`、`total_bytes`、`checksum`（`verified`：md5 校验通过；`unavailable`：服务器没有 `.md5`，只校验了大小）、`error_code`、`error_message`、`retriable`、`resumable`（是否留有可续传的部分文件）。

下载流程：

1. **磁盘预检**：需要的空间 = 剩余待下载大小 + 压缩包解压估算 + `reserve_bytes`，不够直接返回 `disk_insufficient`，details 中给出 `required_bytes` / `free_bytes`。
2. **断点续传**：下载写到 `<文件>.gwpart`，用 HTTP Range + ETag 续传。网络中断、gateway 重启后再次调用下载接口会从断点继续；服务器文件已变化时自动从头下载。
3. **重定向保护**：拒绝 https→http 降级跳转，限制跳转次数（`max_redirects`）。
4. **校验**：大小必须与服务器声明一致；服务器有 `<url>.md5` 时边下载边计算 md5，下载完比对，不一致就删除文件并返回 `checksum_mismatch`。
5. **压缩包**：解压到临时目录，检查必需文件，再替换进模型目录，失败不会留下半成品；解压后删除压缩包。

模型路径保持不变：仍是 `~/.cache/models/<domain>/` 下各 SDK 的默认位置，以运行 gateway 的用户的 HOME 为准。

注意：

- 以上下载保障按 archive.spacemit.com 的行为设计（支持 HEAD、提供 ETag、没有 md5 时返回 404）。通过 `register` 注册的第三方地址（如 ModelScope）不保证续传、磁盘预检和 md5 校验，可能直接下载失败。
- Matcha TTS 由声码器和声学模型两个文件组成，`progress` 按文件分段计算，中途会回落；是否下载完成以 `status` 为准。

```yaml
# configs/base.yaml
download:
  tls_verify: true             # 校验服务器证书
  reserve_bytes: 1073741824    # 下载后磁盘至少保留 1 GiB
  archive_extract_ratio: 1.0   # 解压后体积估算 = 压缩包大小 × 该值
  verify_md5: true
  connect_timeout_s: 30
  read_timeout_s: 60
  max_redirects: 5
```

### 错误码

所有接口的错误响应格式统一为 `{"error": <code>, "message", "retriable", "details"}`；Vision 保留原有整数 `code` 包装，额外带字符串字段 `error`。下载失败的 `error_code` 也取自同一清单。

`GET /v1/errors` 返回完整清单，每项包含：错误码、阶段（`download`/`download_api`/`load`/`inference`/`request`）、HTTP 状态码、是否可重试、触发条件、建议处理。常用错误码：

| 阶段 | 错误码 |
|------|--------|
| 下载 | `disk_insufficient`、`network_error`、`remote_http_error`、`tls_error`、`redirect_blocked`、`size_mismatch`、`checksum_mismatch`、`extract_failed`、`permission_denied`、`io_error` |
| 加载 | `model_not_downloaded`、`model_downloading`、`load_oom`、`load_invalid_model`、`load_invalid_args`、`load_timeout`、`backend_missing`、`load_failed` |
| 推理 | `model_not_loaded`、`backend_crashed`、`upstream_error`、`inference_failed`（Vision） |

流式请求（`stream: true`）在响应头发出后失败时（如推理进程中途崩溃），HTTP 状态码已经是 200，错误以流里的最后一帧给出，帧内 `code` 同上表：

| 接口 | 错误帧 |
|------|--------|
| OpenAI 兼容（`/chat/completions`、`/completions`、VLM） | `data: {"error": {"code", "message", "retriable", "details"}}` |
| Anthropic `/v1/messages`、`/v1/responses` | `event: error` + `data: {"type": "error", ...}` |
| Ollama `/api/chat` | `{"error", "code", "retriable", "done": true}` |

本地模型为 `backend_crashed`（下一次请求会自动尝试重新拉起推理进程），remote 模型为 `upstream_error`。

llama-server（LLM/Embed/Rerank/VLM）的输出写到 `~/.cache/spacemit-ai-gateway/<domain>/logs/<model>.log`（10 MiB 滚动，保留一份 `.log.1`）。加载失败和 `backend_crashed` 时，错误的 `details.log_tail` 附带最后几行日志，`details.log_path` 给出日志文件位置。

### 模型故障记录

`GET /v1/errors/recent` 返回最近发生的模型故障，用于集成方查询"哪个模型出了什么错"，新的在前：

```bash
curl -s 'localhost:18790/v1/errors/recent?domain=llm&model=qwen3-0.6b-q4_0&limit=20'
```

| 参数 | 说明 |
|------|------|
| `domain` | `asr` / `tts` / `vad` / `vision` / `llm` / `embed` / `rerank` / `vlm`，不填返回全部 |
| `model` | 模型 ID |
| `since` | Unix 时间戳，只返回之后的记录（轮询时传上次拿到的最大 `ts`） |
| `limit` | 1–2000，默认 100 |

```json
{"errors": [{"ts": 1791367600.12, "time": "2026-10-07T18:06:40+08:00", "domain": "llm",
             "model": "qwen3-0.6b-q4_0", "code": "backend_crashed", "phase": "inference",
             "message": "...", "retriable": true, "details": {"log_tail": ["..."]}}]}
```

- 只记模型故障：`phase` 为 `download` / `load` / `inference` 的错误（`code` 含义见 `GET /v1/errors`）。调用方参数错误、未知模型、模型未下载 / 正在下载 / 未加载、用户取消下载不记。
- 覆盖：八个域的下载失败（手动下载和加载时自动下载）、加载失败、推理失败，包括流式中途的错误帧和 ASR/TTS/VAD 的 WebSocket 流。Vision 记录 `/v1/vision/models/load`、`/v1/vision/inference` 和视频流 WebSocket；离线 jobs / sequence / feature 接口不记。
- 同一次故障只记一条。加载时自动下载失败记为下载故障，不再另记一条加载故障。
- 存储：`~/.cache/spacemit-ai-gateway/errors.sqlite`，只保留最近 2000 条，gateway 或开发板重启后仍可查询。数据库不可写时退回内存记录，不影响业务请求。

### 鉴权与 IP 白名单

默认不启用鉴权或 IP 白名单。生产环境如需限制访问，先开启 `auth.enabled`，再配置 API Key 或外部白名单文件。白名单文件修改后自动热加载，无需重启：

```yaml
# configs/base.yaml
auth:
  enabled: true
  api_keys:
    - "your-api-key"
  ip_whitelist_file: "configs/ip_whitelist.txt"
```

```text
# configs/ip_whitelist.txt（已 gitignore，不会进仓库）
127.0.0.1
192.168.1.0/24
10.0.91.5
```

`auth.enabled: false` 时不限制访问；白名单文件为空或未配置时只校验 API Key。

## 集成指南

上层服务对接 gateway 的完整流程。字段细节见[模型下载](#模型下载)、[错误码](#错误码)、[模型故障记录](#模型故障记录)，各域全部接口见[功能概览](#功能概览)。

```bash
B=http://<设备 IP>:18790
# 开启鉴权（auth.enabled: true）时，每个请求加 -H 'X-API-Key: <key>'
```

```
GET /models 查是否已下载 → POST .../download 开始下载 → GET .../download 轮询到下载完成
  → POST /models/load 加载（可省略，Vision 除外） → 推理 → 失败时按错误码处理，事后用 /v1/errors/recent 查
```

### 两类域的差异

| | LLM / Embed / Rerank / VLM | ASR / TTS / VAD / Vision |
|---|---|---|
| `GET /models` 中的下载状态 | `status`：`available` / `downloading` / `downloaded` / `loading` / `loaded` / `error` | `downloaded`：`true` / `false` |
| 未下载时加载或推理 | 返回 `model_not_downloaded`，需先调下载接口 | 加载时自动下载（ASR/TTS/VAD 首次推理也会触发），这次请求会慢 |
| 加载请求体 | `{"model": "<id>"}` | `{"model_id": "<id>"}` |
| 下载记录 | 存 SQLite，gateway 重启后进度和 `checksum` 仍在 | 存内存，重启后已下载的模型只返回 `status: downloaded`，`downloaded_bytes` 为 0，`total_bytes`、`checksum` 为空 |
| 响应格式 | 直接返回字段 | ASR/TTS/VAD 直接返回；Vision 包在 `{"code", "message", "request_id", "data"}` 的 `data` 里 |

### 1. 下载与进度

```bash
curl -s -X POST $B/v1/llm/models/qwen3-0.6b-q4_0/download    # 立即返回，后台下载
curl -s $B/v1/llm/models/qwen3-0.6b-q4_0/download             # 轮询进度，1–2 秒一次即可
```

```json
{"model": "qwen3-0.6b-q4_0", "status": "downloaded", "progress": 1.0,
 "downloaded_bytes": 382156160, "total_bytes": 382156160, "checksum": "verified",
 "error_code": null, "error_message": null, "retriable": null, "resumable": false}
```

其他域只换路径：`/v1/{asr,tts,vad,embed,rerank,vlm}/models/<id>/download`、`/v1/vision/models/<id>/download`。按 `status` 判断：

- `downloaded`：完成。LLM 类模型加载后这里会变成 `loading` / `loaded`，同样表示文件已就绪。
- `downloading`：看 `progress`（0–1）或 `downloaded_bytes` / `total_bytes`。
- `error`：看 `error_code`。`retriable: true` 时重新 POST 下载即可，`resumable: true` 表示会从断点续传。
- `available` 且 `resumable: true`：上次下载中断了（如 gateway 重启），重新 POST 即续传。
- 不由 gateway 下载的模型（ASR `qwen3-asr`、TTS `kokoro`）返回 `download_not_supported`，由对应 SDK 自行下载。

### 2. 加载

```bash
curl -s -X POST $B/v1/llm/models/load -H 'Content-Type: application/json' -d '{"model":"qwen3-0.6b-q4_0"}'
# {"model":"qwen3-0.6b-q4_0","status":"loaded"}
curl -s -X POST $B/v1/tts/models/load -H 'Content-Type: application/json' -d '{"model_id":"matcha_zh_en"}'
# {"loaded":true,"model_id":"matcha_zh_en","state":"ready"}
```

- 除 Vision 外都可以不显式加载，第一次推理会自动加载，只是这次请求会慢。Vision 推理前必须调 `POST /v1/vision/models/load`。
- 判断是否已加载看 `GET /models`：LLM 类看 `status: loaded`，ASR/TTS/VAD 看 `loaded: true`。
- LLM 类的 `/healthz` 显示的是"当前活跃模型"，由第一次推理或 `POST /models/switch` 设置，`load` 不会改变它，所以不要用它判断是否已加载。

### 3. 推理

```bash
# TTS：合成 wav
curl -s -X POST $B/v1/tts/synthesize -H 'Content-Type: application/json' \
  -d '{"text":"你好，欢迎使用语音合成服务。","model":"matcha_zh_en"}' -o hello.wav
# ASR：识别音频文件
curl -s -X POST $B/v1/asr/recognize -F file=@hello.wav -F model=sensevoice
# VAD
curl -s -X POST $B/v1/vad/analyze -F file=@hello.wav
# LLM（OpenAI 兼容；加 "stream": true 为 SSE 流式）
curl -s -X POST $B/v1/llm/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-0.6b-q4_0","messages":[{"role":"user","content":"1+1=?"}],"max_tokens":32}'
# Embed
curl -s -X POST $B/v1/embed/embeddings -H 'Content-Type: application/json' \
  -d '{"model":"bge-small-zh-v1.5-q4_k_m","input":"你好"}'
# Vision（先 load）
curl -s -X POST $B/v1/vision/inference -F file=@image.jpg -F 'tasks=["detect"]' -F model_id=yolov8n
```

Rerank 为 `POST /v1/rerank/rerank`，VLM 为 `POST /v1/vlm/chat/completions`（OpenAI 图文消息格式）。流式接口（ASR/TTS/VAD 的 WebSocket、Vision 视频流）见[功能概览](#功能概览)。

### 4. 错误处理

- **同步请求**：HTTP 状态码非 2xx，响应体为 `{"error": <错误码>, "message", "retriable", "details"}`（Vision 另带整数 `code`）。`GET /v1/errors` 里每个错误码都有 `action`（建议处理），上层可以直接按错误码做映射。常见的几种：

  | 错误码 | 上层处理 |
  |---|---|
  | `model_not_downloaded` / `model_downloading` | 先下载 / 等下载完成再重试 |
  | `disk_insufficient` | 清理磁盘，`details` 给出 `required_bytes` / `free_bytes` |
  | `network_error` | 重新下载，已下载部分会续传 |
  | `checksum_mismatch` | 重新下载（校验失败的文件已删除，从头下载） |
  | `load_oom` | 卸载其他模型或换更小的模型 |
  | `backend_crashed` | 直接重试，gateway 会重新拉起推理进程 |

- **流式请求**：响应头发出后才失败时（如推理进程中途崩溃），HTTP 状态码已是 200，错误在流的最后一帧（格式见[错误码](#错误码)），收到错误帧就按失败处理。
- **事后查询**：`GET /v1/errors/recent` 返回各模型最近的下载、加载、推理故障，gateway 或设备重启后仍可查询。定期轮询时，把上次结果中最大的 `ts` 作为 `since` 传入，只拿新增记录：

  ```bash
  curl -s "$B/v1/errors/recent?since=1791367600.12"
  ```

## 前端控制台

`frontend/` 目录包含一个纯静态的 SPA 管理界面（CDN React 18 + Babel standalone，无需构建），提供以下功能：

- **仪表盘** — 服务状态总览、引擎信息、硬件状态
- **模型管理** — 查看/加载/卸载/切换默认模型（ASR/TTS/VAD/Vision）
- **LLM / Embed / Rerank 管理** — GGUF 模型下载/加载/卸载/注册/注销、下载进度跟踪
- **在线体验** — ASR 语音识别、TTS 语音合成、VAD 语音活动检测、YOLO 目标检测
- **LLM Playground** — 大语言模型对话、模型切换、流式/非流式输出、参数调节
- **系统配置** — ASR/TTS/VAD 推理参数在线调整
- **词库管理** — ASR 热词、TTS 发音词库的增删管理
- **异步任务** — 查看/取消异步转写和合成任务
- **中英切换 / 主题切换** — 顶部工具栏支持语言和亮色/暗色/跟随系统主题切换

### 启动前端

前端为纯静态文件，任意 HTTP 服务器均可托管：

```bash
# 方式一：Python 内置 HTTP 服务器（开发用）
cd frontend
python3 -m http.server 8326

# 方式二：nginx（生产推荐）
# 将 frontend/ 目录配置为 nginx root 即可
```

然后浏览器访问 `http://<设备IP>:8326` 即可打开控制台。

### 连接后端

前端默认自动连接与页面同 hostname 的后端服务（端口 `18790`），无需额外配置。如果后端运行在其他地址，编辑 `frontend/src/config.js`：

```js
window.API_BASES = {
  asr:    'http://<后端IP>:18790',
  tts:    'http://<后端IP>:18790',
  vad:    'http://<后端IP>:18790',
  vision: 'http://<后端IP>:18790',
  llm:    'http://<后端IP>:18790',
  embed:  'http://<后端IP>:18790',
  rerank: 'http://<后端IP>:18790',
};
```

### Mock 模式

后端未启动时，前端会自动降级为 Mock 数据展示。也可手动开启：

```js
// frontend/src/config.js
window.USE_MOCK = true;
```

## 项目结构

```
spacemit-ai-gateway/
├── frontend/                   # 前端管理控制台（纯静态 SPA）
│   ├── index.html              # 入口
│   └── src/
│       ├── config.js           # API 地址配置
│       ├── i18n.js             # 中英翻译映射
│       ├── api.js              # 后端 API 封装
│       ├── mockData.js         # 离线 Mock 数据
│       ├── styles.css          # 全局样式
│       ├── App.jsx             # 路由 + 布局
│       ├── Sidebar.jsx         # 侧边导航
│       ├── DashboardPages.jsx  # 仪表盘、历史、模型管理、设置
│       ├── ConfigPage.jsx      # 系统配置
│       ├── LexiconPage.jsx     # 词库管理
│       ├── TasksPage.jsx       # 异步任务
│       ├── ASRTryPage.jsx      # ASR 体验
│       ├── TTSTryPage.jsx      # TTS 体验
│       ├── VADTryPage.jsx      # VAD 体验
│       ├── YoloTryPage.jsx     # YOLO 体验
│       ├── PlaygroundPage.jsx  # LLM/VLM Playground
│       ├── LLMManagePage.jsx   # LLM 模型管理
│       ├── ResourceMonitorPage.jsx # 资源监控
│       ├── ModelSelectPage.jsx # 模型选择
│       └── Icon.jsx            # 图标组件
├── configs/                    # 配置文件
│   ├── base.yaml
│   ├── dev.yaml
│   └── vision/                 # 视觉模型配置
├── schema/                     # 模型清单 schema
├── src/spacemit_ai_gateway/
│   ├── app/                    # 应用入口、生命周期、配置
│   ├── common/                 # 共享模块（errors, sessions, task_store, lexicon_store）
│   ├── gateway/                # 鉴权、依赖注入、错误处理、健康检查
│   └── domains/
│       ├── asr/                # 语音识别
│       │   ├── api.py          # HTTP 路由
│       │   ├── stream.py       # WebSocket 路由
│       │   ├── service.py      # 业务编排
│       │   ├── schemas.py      # 请求/响应模型
│       │   └── adapters/       # 后端实现（sensevoice, qwen3_asr）
│       ├── tts/                # 语音合成（matcha, kokoro）
│       ├── vad/                # 语音活动检测（silero）
│       ├── llm/                # 大语言模型
│       │   ├── api.py          # OpenAI/Ollama/Anthropic 兼容路由
│       │   ├── service.py      # 模型生命周期管理（SQLite 注册表）
│       │   ├── schemas.py      # 请求/响应模型
│       │   └── adapters/       # llama-server 本地 + 远程 API 代理
│       ├── embed/              # 文本嵌入
│       ├── rerank/             # 文本重排序
│       └── vision/             # 视觉处理
├── tests/                      # 测试
└── pyproject.toml
```

## API 文档

启动后访问：

- Swagger UI: http://localhost:18790/docs
- ReDoc: http://localhost:18790/redoc
- OpenAPI JSON: http://localhost:18790/openapi.json

## 附录：K3 实测性能参考

以下数据来自 K3 真机测试记录，仅作为部署选型和容量预估参考。核数/线程数以测试时的
`/engine` 返回、配置项或测试命令为准；LLM 数据来自 `llama-bench -t 4`，不包含 TTFT。

| 域 | 后端 / 模型 | 接口或测试项 | 核 / 线程配置 | 输入规模 | 实测指标 |
|----|-------------|--------------|---------------|----------|----------|
| ASR | SenseVoice | 文件识别代表值 | `num_threads=1`, `device=spacemit` | 1.80s 音频 | 处理 0.232s, RTF 0.129 |
| TTS | Matcha ZH | HTTP `/v1/tts/synthesize` | `threads=1` | 生成 3.32s 音频 | 处理 1.56s, RTF 0.47 |
| TTS | Matcha ZH | WS `/v1/tts/stream` | `threads=1` | 生成 4.56s 音频 | 处理 2.17s, RTF 0.48 |
| VAD | Silero VAD | `vad_simple_demo` | `threads=1` | 224.00ms 音频 | 处理 6.339ms, RTF 0.0283 |
| Vision | YOLOv8n detect | `/v1/vision/inference` / `/stats` | `ai_core_group=cluster0`, `threads=4` | 640x640 图像 | `infer_ms=22.82`, 约 43.8 FPS |
| LLM | Qwen2.5-0.5B Q4_0 | `llama-bench` | `threads=4` | `pp512`, `tg128` | PP 155.61 tok/s, TG 43.71 tok/s |
| LLM | Qwen3-0.6B Q4_0 | `llama-bench` | `threads=4` | `pp512`, `tg128` | PP 108.81 tok/s, TG 31.74 tok/s |
| LLM | Qwen3.5-0.8B Q4_0 | `llama-bench` | `threads=4` | `pp512`, `tg128` | PP 40.55 tok/s, TG 23.38 tok/s |
| LLM | DeepSeek-R1-Distill-Qwen-1.5B Q4_0 | `llama-bench` | `threads=4` | `pp512`, `tg128` | PP 80.15 tok/s, TG 18.77 tok/s |

## 测试

```bash
# 单元测试
pytest tests/
```

## 功能概览

### ASR 语音识别 (`/v1/asr`)

| 类别 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 核心 | POST | `/recognize` | 同步语音识别 |
| 核心 | WS | `/stream` | 流式语音识别 |
| 核心 | POST | `/stream/session` | 申请流式会话 |
| 核心 | GET | `/models` | 模型列表 |
| 核心 | POST | `/models/load` | 加载模型 |
| 核心 | POST | `/models/unload` | 卸载模型 |
| 核心 | POST | `/models/switch` | 切换默认模型 |
| 核心 | GET | `/languages` | 支持语种 |
| 下载 | POST/GET/DELETE | `/models/{id}/download` | 下载 / 查询进度 / 取消（见[模型下载](#模型下载)） |
| 异步 | POST | `/jobs` | 提交异步转写任务 |
| 异步 | GET | `/jobs/{id}` | 查询任务状态 |
| 异步 | DELETE | `/jobs/{id}` | 取消任务 |
| 词库 | GET | `/lexicons` | 热词词库列表 |
| 词库 | POST | `/lexicons` | 创建热词词库 |
| 运维 | GET | `/healthz` | 健康检查 |
| 运维 | GET/PATCH | `/params` | 推理参数 |
| 运维 | GET/PATCH | `/audio` | 音频预处理配置 |
| 运维 | GET/PATCH | `/engine` | 引擎配置 |
| 运维 | GET | `/stats` | 性能指标 |
| 运维 | GET | `/info` | 运行态摘要 |

### TTS 语音合成 (`/v1/tts`)

| 类别 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 核心 | POST | `/synthesize` | 同步语音合成 |
| 核心 | WS | `/stream` | 流式语音合成 |
| 核心 | POST | `/stream/session` | 申请流式会话 |
| 核心 | GET | `/voices` | 音色列表 |
| 核心 | GET | `/models` | 模型列表 |
| 核心 | POST | `/models/load` | 加载模型 |
| 核心 | POST | `/models/unload` | 卸载模型 |
| 核心 | POST | `/models/switch` | 切换默认模型 |
| 下载 | POST/GET/DELETE | `/models/{id}/download` | 下载 / 查询进度 / 取消（见[模型下载](#模型下载)） |
| 异步 | POST | `/tasks` | 提交异步合成任务 |
| 异步 | GET | `/tasks/{id}` | 查询任务状态 |
| 异步 | DELETE | `/tasks/{id}` | 取消任务 |
| 异步 | GET | `/tasks/{id}/audio` | 下载合成音频 |
| 词库 | GET | `/lexicons` | 发音词库列表 |
| 词库 | POST | `/lexicons` | 创建发音词库 |
| 运维 | GET | `/healthz` | 健康检查 |
| 运维 | GET/PATCH | `/params` | 推理参数 |
| 运维 | GET/PATCH | `/engine` | 引擎配置 |
| 运维 | GET | `/stats` | 性能指标 |
| 运维 | GET | `/info` | 运行态摘要 |

### VAD 语音活动检测 (`/v1/vad`)

| 类别 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 核心 | POST | `/analyze` | 短片段语音检测 |
| 核心 | POST | `/segments` | 音频切分 |
| 核心 | WS | `/stream` | 流式检测 |
| 核心 | GET | `/models` | 模型列表 |
| 核心 | POST | `/models/load` | 加载模型 |
| 核心 | POST | `/models/unload` | 卸载模型 |
| 核心 | POST | `/models/switch` | 切换默认模型 |
| 下载 | POST/GET/DELETE | `/models/{id}/download` | 下载 / 查询进度 / 取消（见[模型下载](#模型下载)） |
| 运维 | GET | `/healthz` | 健康检查 |
| 运维 | GET/PATCH | `/params` | 推理参数 |
| 运维 | GET/PATCH | `/audio` | 音频预处理配置 |
| 运维 | GET/PATCH | `/engine` | 引擎配置 |
| 运维 | GET | `/stats` | 性能指标 |
| 运维 | GET | `/info` | 运行态摘要 |

### Vision 视觉处理 (`/v1/vision`)

视觉域支持目标检测、人脸识别、姿态估计、语义分割、目标跟踪等，基于 SpaceMIT EP 加速推理。

| 类别 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 推理 | POST | `/inference` | 图像推理（检测/分类/分割/姿态） |
| 推理 | POST | `/feature` | 特征提取（embedding / similarity） |
| 推理 | POST | `/sequence` | 序列推理 |
| 流式 | WS | `/stream` | 实时视频流推理 |
| 流式 | DELETE | `/stream/{id}` | 删除流式会话 |
| 异步 | POST | `/jobs` | 提交批量推理任务 |
| 异步 | GET | `/jobs/{id}` | 查询任务状态 |
| 异步 | DELETE | `/jobs/{id}` | 取消任务 |
| 模型 | GET | `/models` | 模型列表（支持 tags/backend 过滤） |
| 模型 | POST | `/models/load` | 加载模型（自动下载） |
| 模型 | POST | `/models/unload` | 卸载模型 |
| 模型 | POST | `/models/switch` | 切换默认模型 |
| 下载 | POST/GET/DELETE | `/models/{id}/download` | 下载 / 查询进度 / 取消（见[模型下载](#模型下载)） |
| 运维 | GET | `/healthz` | 健康检查 |
| 运维 | GET/PATCH | `/params` | 推理参数 |
| 运维 | GET/PATCH | `/engine` | 引擎配置 |
| 运维 | GET | `/stats` | 性能指标 |

**预置模型**：`model_id` 与 `configs/vision/<model_id>.yaml` 对应；内置快捷加载含 `yolov8n`/`yolov8s`/`yolov8m`、`yolov8n-pose`…`yolov8m-pose`、`yolov8n-seg`…`yolov8m-seg`、`yolov11n`/`yolov11s`/`yolov11m`、`yolov5-face`、`yolov5-gesture`、`resnet50`、`emotion`、`arcface`、`bytetrack`、`ocsort`，以及目录内其余 YAML 自动发现。

### LLM 大语言模型 (`/v1/llm`)

基于 llama-server 的 LLM 推理网关，支持本地 GGUF 模型和远程 API 代理，兼容 OpenAI / Ollama / Anthropic 协议。

| 类别 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 推理 | POST | `/chat/completions` | 对话补全（支持 SSE 流式） |
| 推理 | POST | `/completions` | 文本补全 |
| 模型 | GET | `/models` | 模型列表（含状态、来源、下载进度） |
| 模型 | POST | `/models/register` | 注册模型（remote / local_url / local_path） |
| 模型 | POST | `/models/deregister` | 注销自定义模型 |
| 模型 | POST | `/models/load` | 加载模型（启动 llama-server 进程） |
| 模型 | POST | `/models/unload` | 卸载模型（停止进程） |
| 模型 | POST | `/models/switch` | 切换活跃模型 |
| 下载 | POST | `/models/{id}/download` | 开始下载 |
| 下载 | GET | `/models/{id}/download` | 查询下载进度 |
| 下载 | DELETE | `/models/{id}/download` | 取消下载 |
| 兼容 | POST | `/api/chat` | Ollama 协议兼容 |
| 兼容 | POST | `/api/generate` | Ollama 补全 |
| 兼容 | GET | `/api/tags` | Ollama 模型列表 |
| 运维 | GET | `/healthz` | 健康检查 |
| 运维 | GET | `/metrics` | Prometheus 指标 |

**模型生命周期**：`available` → `downloading` → `downloaded` → `loading` → `loaded`；下载失败为 `error`（原因见 `GET /models/{id}/download`），重新下载即可。

### VLM 视觉语言模型 (`/v1/vlm`)

基于 OpenAI 兼容 VLM 接口的视觉语言模型网关，支持本地 llama-server 启动和远程 API 代理两种模式。`model-zoo/vlm` 中的 VLM 推理组件可作为本地或远程服务源。

| 类别 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 推理 | POST | `/v1/vlm/chat/completions` | OpenAI 兼容视觉语言推理（支持 SSE 流式） |
| 模型 | GET | `/v1/vlm/models` | 模型列表 |
| 模型 | POST | `/v1/vlm/models/register` | 注册 VLM 模型（remote / local_url / local_path） |
| 模型 | POST | `/v1/vlm/models/deregister` | 注销 VLM 模型 |
| 模型 | POST | `/v1/vlm/models/load` | 加载 / 激活模型 |
| 模型 | POST | `/v1/vlm/models/unload` | 卸载模型 |
| 模型 | POST | `/v1/vlm/models/switch` | 切换活跃模型 |
| 下载 | POST/GET/DELETE | `/v1/vlm/models/{id}/download` | 下载 / 查询进度 / 取消 |
| 运维 | GET | `/v1/vlm/healthz` | VLM 健康检查 |

**注册模式说明**：
- `source_type=remote`：注册远程 OpenAI 兼容 VLM 推理服务，需提供 `api_base_url` 和可选 `api_key`。
- `source_type=local_path`：注册本地模型目录，Gateway 会启动 llama-server 进程进行推理。
- `source_type=local_url`：注册本地已运行的 llama-server 实例地址。

### Embed 文本嵌入 (`/v1/embed`)

基于 llama-server `--embedding` 的文本嵌入网关，支持本地 GGUF 模型和远程 API 代理，兼容 OpenAI embeddings 协议。

| 类别 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 推理 | POST | `/embeddings` | 文本向量生成 |
| 模型 | GET | `/models` | 模型列表（含状态、来源、下载进度） |
| 模型 | POST | `/models/register` | 注册模型（remote / local_url / local_path） |
| 模型 | POST | `/models/deregister` | 注销自定义模型 |
| 模型 | POST | `/models/load` | 加载模型（启动 llama-server 进程） |
| 模型 | POST | `/models/unload` | 卸载模型（停止进程） |
| 模型 | POST | `/models/switch` | 切换活跃模型 |
| 下载 | POST | `/models/{id}/download` | 开始下载 |
| 下载 | GET | `/models/{id}/download` | 查询下载进度 |
| 下载 | DELETE | `/models/{id}/download` | 取消下载 |
| 运维 | GET | `/healthz` | 健康检查 |

**协议兼容路由**（无 `/v1/embed` 前缀）：`POST /v1/embeddings`

### Rerank 文本重排序 (`/v1/rerank`)

基于 llama-server `--reranking` 的文本重排序网关，支持本地 GGUF 模型和远程 API 代理。

| 类别 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 推理 | POST | `/rerank` | 文本重排序 |
| 模型 | GET | `/models` | 模型列表（含状态、来源、下载进度） |
| 模型 | POST | `/models/register` | 注册模型（remote / local_url / local_path） |
| 模型 | POST | `/models/deregister` | 注销自定义模型 |
| 模型 | POST | `/models/load` | 加载模型（启动 llama-server 进程） |
| 模型 | POST | `/models/unload` | 卸载模型（停止进程） |
| 模型 | POST | `/models/switch` | 切换活跃模型 |
| 下载 | POST | `/models/{id}/download` | 开始下载 |
| 下载 | GET | `/models/{id}/download` | 查询下载进度 |
| 下载 | DELETE | `/models/{id}/download` | 取消下载 |
| 运维 | GET | `/healthz` | 健康检查 |

**协议兼容路由**（无 `/v1/rerank` 前缀）：`POST /v1/rerank`

### Gateway

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/healthz` | 聚合健康检查（ASR + TTS + VAD + LLM + VLM + Vision） |
| GET | `/v1/errors` | 错误码清单（见[错误码](#错误码)） |
| GET | `/v1/errors/recent` | 最近的模型故障，可按域 / 模型 / 时间过滤（见[模型故障记录](#模型故障记录)） |

### 多后端支持

ASR / TTS / VAD / Vision / LLM / Embed / Rerank 均支持多后端，可通过 `models/load`、`models/unload`、`models/switch` 动态管理，请求时通过 `model` 字段路由：

- **ASR**: `sensevoice`（默认）、`qwen3-asr`
- **TTS**: `matcha_zh`（默认）、`matcha_en`、`matcha_zh_en`、`kokoro`
- **VAD**: `silero`（默认）
- **Vision**: 多组 `configs/vision/*.yaml`（YOLOv8/v11 多档位与 pose/seg、YOLOv5 人脸/手势、ResNet、跟踪等），通过 `model_id` / `models/load` 管理
- **LLM**: 16 个预设 GGUF 模型（Qwen3/3.5、Qwen2.5、DeepSeek、GLM 等），支持运行时注册远程 API 或本地模型
- **Embed**: 6 个预设 GGUF 嵌入模型（BGE、Jina、Nomic、Qwen3 Embedding），支持运行时注册远程 API 或本地模型
- **Rerank**: 2 个预设 GGUF 重排序模型（BGE Reranker、Qwen3 Reranker），支持运行时注册远程 API 或本地模型

## License

Apache-2.0
