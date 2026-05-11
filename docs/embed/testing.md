# SpacemiT AI Gateway Embed 测试记录

> 测试环境：Linux x86_64，Python 3.x，服务监听 `localhost:18790`
> 默认模型：`nomic-embed-text-v2-moe-q4_0`（preset，启动时自动下载并加载）

---

## 环境准备

```bash
git clone git@gitlab.dc.com:bianbu/spacemit_claw/spacemit-ai-gateway.git
cd spacemit-ai-gateway
python3 -m venv .venv
.venv/bin/pip install -e .
```

### 启动服务

```bash
.venv/bin/uvicorn spacemit_ai_gateway.app.main:app --host 0.0.0.0 --port 18790
```

服务启动后 Swagger 文档：http://localhost:18790/docs

### 清理工具

```bash
./scripts/embed/clean.sh db      # 删除数据库
./scripts/embed/clean.sh models  # 删除所有模型文件
./scripts/embed/clean.sh kill    # 杀掉 18790 端口进程
./scripts/embed/clean.sh all     # 全部清理
```

### 模型来源说明

| source_type  | 说明                                        |
|--------------|---------------------------------------------|
| `local_path` | 本地 GGUF 文件，直接加载                    |
| `local_url`  | 远程 GGUF，下载后缓存到本地再启动           |
| `remote`     | 透传到外部 OpenAI 兼容 API，不启动本地进程  |

---

## 自动下载与加载

服务启动时，若 `configs/base.yaml` 中配置了 `embed.backend`，会自动：

1. 检查模型文件是否已在 `~/.cache/models/embed/` 中
2. 文件存在 → 直接加载
3. 文件不存在 → 后台下载，完成后自动加载（不阻塞服务启动）

启动日志示例：

```
[autoload] default_model 'nomic-embed-text-v2-moe-q4_0' not downloaded, starting background download
[autoload] download complete for 'nomic-embed-text-v2-moe-q4_0', loading...
[autoload] 'nomic-embed-text-v2-moe-q4_0' loaded and active
```

---

## 全局健康检查

```bash
curl -s localhost:18790/healthz | jq .
```

```json
{
  "status": "healthy",
  "domains": {
    "asr":    { "ready": true,  "state": "ready", "backend": "sensevoice (mock)" },
    "tts":    { "ready": true,  "state": "ready", "backend": "matcha_zh (mock)"  },
    "vad":    { "ready": true,  "state": "ready", "backend": "silero (mock)"     },
    "llm":    { "ready": true,  "state": "ready", "backend": "qwen3-0.6b-q4_0"  },
    "embed":  { "ready": true,  "state": "ready", "backend": "nomic-embed-text-v2-moe-q4_0" },
    "vision": { "ready": false, "state": "uninitialized","backend": "unknown"   }
  }
}
```

---

## Embed 健康检查

```bash
curl -s localhost:18790/v1/embed/healthz | jq .
```

模型已加载：

```json
{ "status": "ready", "model": "nomic-embed-text-v2-moe-q4_0" }
```

无模型加载时：

```json
{ "status": "failed", "model": null }
```

---

## 模型管理

### 列出模型

```bash
curl -s localhost:18790/v1/embed/models | jq .
```

```json
[
  {
    "id": "bge-small-zh-v1.5-q4_k_m",
    "source_type": "local_url",
    "url": "https://archive.spacemit.com/spacemit-ai/model_zoo/embed/Bge-Small-Zh-V1.5-Q4_K_M.gguf",
    "local_path": null,
    "status": "available",
    "is_preset": 1,
    "download_progress": 0.0
  },
  {
    "id": "nomic-embed-text-v2-moe-q4_0",
    "source_type": "local_url",
    "url": "https://archive.spacemit.com/spacemit-ai/model_zoo/embed/Nomic-Embed-Text-V2-Moe-Q4_0.gguf",
    "local_path": "/home/liudecheng/.cache/spacemit-ai-gateway/embed/models/nomic-embed-text-v2-moe-q4_0.gguf",
    "status": "loaded",
    "is_preset": 1,
    "download_progress": 1.0
  }
]
```

### 注册模型（local_path）

```bash
curl -s -X POST localhost:18790/v1/embed/models/register \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "test-local",
    "source_type": "local_path",
    "local_path": "/path/to/embed-model.gguf"
  }' | jq .
```

```json
{ "model": "test-local", "status": "downloaded" }
```

### 注册模型（remote）

```bash
curl -s -X POST localhost:18790/v1/embed/models/register \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "test-remote",
    "source_type": "remote",
    "api_base_url": "https://api.openai.com/v1",
    "api_key": "sk-xxx"
  }' | jq .
```

```json
{ "model": "test-remote", "status": "loaded" }
```

### 加载模型

```bash
curl -s -X POST localhost:18790/v1/embed/models/load \
  -H 'Content-Type: application/json' \
  -d '{"model": "nomic-embed-text-v2-moe-q4_0"}' | jq .
```

```json
{ "model": "nomic-embed-text-v2-moe-q4_0", "status": "loaded" }
```

附加 llama-server 参数：

```bash
curl -s -X POST localhost:18790/v1/embed/models/load \
  -H 'Content-Type: application/json' \
  -d '{"model": "nomic-embed-text-v2-moe-q4_0", "extra_args": ["--threads", "4"]}' | jq .
```

### 卸载模型

```bash
curl -s -X POST localhost:18790/v1/embed/models/unload \
  -H 'Content-Type: application/json' \
  -d '{"model": "nomic-embed-text-v2-moe-q4_0"}' | jq .
```

```json
{ "model": "nomic-embed-text-v2-moe-q4_0", "status": "unloaded" }
```

### 切换模型

```bash
curl -s -X POST localhost:18790/v1/embed/models/switch \
  -H 'Content-Type: application/json' \
  -d '{"model": "bge-small-zh-v1.5-q4_k_m"}' | jq .
```

```json
{ "model": "bge-small-zh-v1.5-q4_k_m", "status": "loaded" }
```

### 注销模型

```bash
curl -s -X POST localhost:18790/v1/embed/models/deregister \
  -H 'Content-Type: application/json' \
  -d '{"model": "test-local"}' | jq .
```

```json
{ "model": "test-local", "status": "deregistered" }
```

---

## 推理接口

### 生成向量（OpenAI 兼容）

```bash
curl -s -X POST localhost:18790/v1/embed/embeddings \
  -H 'Content-Type: application/json' \
  -d '{
    "input": "Hello, world!",
    "model": "nomic-embed-text-v2-moe-q4_0"
  }' | jq .
```

```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [0.123, -0.456, 0.789, ...]
    }
  ],
  "model": "nomic-embed-text-v2-moe-q4_0",
  "usage": {
    "prompt_tokens": 5,
    "total_tokens": 5
  }
}
```

批量输入：

```bash
curl -s -X POST localhost:18790/v1/embed/embeddings \
  -H 'Content-Type: application/json' \
  -d '{
    "input": ["Hello", "World"],
    "model": "nomic-embed-text-v2-moe-q4_0"
  }' | jq .
```

### 无前缀路由（OpenAI 兼容）

```bash
curl -s -X POST localhost:18790/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{
    "input": "Hello, world!",
    "model": "nomic-embed-text-v2-moe-q4_0"
  }' | jq .
```

---

## llama-server 原生接口

### 健康检查

```bash
curl -s localhost:18790/v1/embed/health | jq .
```

```json
{
  "status": "ok",
  "slots_idle": 1,
  "slots_processing": 0
}
```

### 获取模型信息

```bash
curl -s localhost:18790/v1/embed/props | jq .
```

```json
{
  "default_generation_settings": {},
  "total_slots": 1,
  "model_path": "/home/liudecheng/.cache/spacemit-ai-gateway/embed/models/nomic-embed-text-v2-moe-q4_0.gguf"
}
```

### Prometheus 指标

```bash
curl -s localhost:18790/v1/embed/metrics
```

```
# HELP llamacpp:prompt_tokens_total Number of prompt tokens processed.
# TYPE llamacpp:prompt_tokens_total counter
llamacpp:prompt_tokens_total 42

# HELP llamacpp:tokens_predicted_total Number of generation tokens processed.
# TYPE llamacpp:tokens_predicted_total counter
llamacpp:tokens_predicted_total 0
```

---

## 接口覆盖测试

| 域       | 方法   | 路径                              | 状态 | 备注                          |
|----------|--------|-----------------------------------|------|-------------------------------|
| Embed    | GET    | /v1/embed/healthz                 | PASS |                               |
| Embed    | GET    | /v1/embed/models                  | PASS |                               |
| Embed    | POST   | /v1/embed/models/register         | PASS |                               |
| Embed    | POST   | /v1/embed/models/load             | PASS |                               |
| Embed    | POST   | /v1/embed/models/unload           | PASS |                               |
| Embed    | POST   | /v1/embed/models/switch           | PASS |                               |
| Embed    | POST   | /v1/embed/models/deregister       | PASS |                               |
| Embed    | POST   | /v1/embed/embeddings              | PASS |                               |
| Embed    | GET    | /v1/embed/health                  | PASS |                               |
| Embed    | GET    | /v1/embed/props                   | PASS |                               |
| Embed    | GET    | /v1/embed/slots                   | PASS |                               |
| Embed    | GET    | /v1/embed/metrics                 | PASS | Prometheus 格式               |
| OAI 兼容 | POST   | /v1/embeddings                    | PASS |                               |
| OAI 兼容 | POST   | /embeddings                       | PASS |                               |
