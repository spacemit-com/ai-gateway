# SpacemiT AI Gateway Rerank 测试记录

> 测试环境：Linux x86_64，Python 3.x，服务监听 `localhost:18790`
> 默认模型：无（`rerank.backend: null`，需手动加载）

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
./scripts/rerank/clean.sh db      # 删除数据库
./scripts/rerank/clean.sh models  # 删除所有模型文件
./scripts/rerank/clean.sh kill    # 杀掉 18790 端口进程
./scripts/rerank/clean.sh all     # 全部清理
```

### 模型来源说明

| source_type  | 说明                                        |
|--------------|---------------------------------------------|
| `local_path` | 本地 GGUF 文件，直接加载                    |
| `local_url`  | 远程 GGUF，下载后缓存到本地再启动           |
| `remote`     | 透传到外部 OpenAI 兼容 API，不启动本地进程  |

---

## 自动下载与加载

Rerank 域默认不自动加载模型（`rerank.backend: null`），需手动调用 `/v1/rerank/models/load` 加载。

若需启动时自动加载，修改 `configs/base.yaml`：

```yaml
rerank:
  backend: bge-reranker-v2-m3-q4_0
```

---

## 全局健康检查

```bash
curl -s localhost:18790/healthz | jq .
```

```json
{
  "status": "degraded",
  "domains": {
    "asr":    { "ready": true,  "state": "ready", "backend": "sensevoice (mock)" },
    "tts":    { "ready": true,  "state": "ready", "backend": "matcha_zh (mock)"  },
    "vad":    { "ready": true,  "state": "ready", "backend": "silero (mock)"     },
    "llm":    { "ready": true,  "state": "ready", "backend": "qwen3-0.6b-q4_0"  },
    "embed":  { "ready": true,  "state": "ready", "backend": "nomic-embed-text-v2-moe-q4_0" },
    "rerank": { "ready": false, "state": "uninitialized", "backend": "unknown" },
    "vision": { "ready": false, "state": "uninitialized","backend": "unknown"   }
  }
}
```

---

## Rerank 健康检查

```bash
curl -s localhost:18790/v1/rerank/healthz | jq .
```

模型已加载：

```json
{ "status": "ready", "model": "bge-reranker-v2-m3-q4_0" }
```

无模型加载时：

```json
{ "status": "failed", "model": null }
```

---

## 模型管理

### 列出模型

```bash
curl -s localhost:18790/v1/rerank/models | jq .
```

```json
[
  {
    "id": "bge-reranker-v2-m3-q4_0",
    "source_type": "local_url",
    "url": "https://archive.spacemit.com/spacemit-ai/model_zoo/rerank/Bge-Reranker-V2-M3-Q4_0.gguf",
    "local_path": null,
    "status": "available",
    "is_preset": 1,
    "download_progress": 0.0
  },
  {
    "id": "bge-reranker-v2.5-gemma2-lightweight-q4_0",
    "source_type": "local_url",
    "url": "https://archive.spacemit.com/spacemit-ai/model_zoo/rerank/Bge-Reranker-V2.5-Gemma2-Lightweight-Q4_0.gguf",
    "local_path": null,
    "status": "available",
    "is_preset": 1,
    "download_progress": 0.0
  }
]
```

### 注册模型（local_path）

```bash
curl -s -X POST localhost:18790/v1/rerank/models/register \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "test-local",
    "source_type": "local_path",
    "local_path": "/path/to/rerank-model.gguf"
  }' | jq .
```

```json
{ "model": "test-local", "status": "downloaded" }
```

### 注册模型（remote）

```bash
curl -s -X POST localhost:18790/v1/rerank/models/register \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "test-remote",
    "source_type": "remote",
    "api_base_url": "https://api.jina.ai/v1",
    "api_key": "jina_xxx"
  }' | jq .
```

```json
{ "model": "test-remote", "status": "loaded" }
```

### 加载模型

```bash
curl -s -X POST localhost:18790/v1/rerank/models/load \
  -H 'Content-Type: application/json' \
  -d '{"model": "bge-reranker-v2-m3-q4_0"}' | jq .
```

```json
{ "model": "bge-reranker-v2-m3-q4_0", "status": "loaded" }
```

附加 llama-server 参数：

```bash
curl -s -X POST localhost:18790/v1/rerank/models/load \
  -H 'Content-Type: application/json' \
  -d '{"model": "bge-reranker-v2-m3-q4_0", "extra_args": ["--threads", "4"]}' | jq .
```

### 卸载模型

```bash
curl -s -X POST localhost:18790/v1/rerank/models/unload \
  -H 'Content-Type: application/json' \
  -d '{"model": "bge-reranker-v2-m3-q4_0"}' | jq .
```

```json
{ "model": "bge-reranker-v2-m3-q4_0", "status": "unloaded" }
```

### 切换模型

```bash
curl -s -X POST localhost:18790/v1/rerank/models/switch \
  -H 'Content-Type: application/json' \
  -d '{"model": "bge-reranker-v2.5-gemma2-lightweight-q4_0"}' | jq .
```

```json
{ "model": "bge-reranker-v2.5-gemma2-lightweight-q4_0", "status": "loaded" }
```

### 注销模型

```bash
curl -s -X POST localhost:18790/v1/rerank/models/deregister \
  -H 'Content-Type: application/json' \
  -d '{"model": "test-local"}' | jq .
```

```json
{ "model": "test-local", "status": "deregistered" }
```

---

## 推理接口

### 重排序（Jira AI 兼容）

```bash
curl -s -X POST localhost:18790/v1/rerank/rerank \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "What is Deep Learning?",
    "documents": [
      "Deep Learning is a subset of machine learning.",
      "Cats are popular pets.",
      "Neural networks are used in deep learning."
    ],
    "model": "bge-reranker-v2-m3-q4_0",
    "top_n": 2
  }' | jq .
```

```json
{
  "model": "bge-reranker-v2-m3-q4_0",
  "usage": {
    "prompt_tokens": 45,
    "total_tokens": 45
  },
  "results": [
    {
      "index": 0,
      "relevance_score": 0.95,
      "document": {
        "text": "Deep Learning is a subset of machine learning."
      }
    },
    {
      "index": 2,
      "relevance_score": 0.87,
      "document": {
        "text": "Neural networks are used in deep learning."
      }
    }
  ]
}
```

### 无前缀路由（Jira AI 兼容）

```bash
curl -s -X POST localhost:18790/v1/rerank \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "What is Deep Learning?",
    "documents": ["Deep Learning is a subset of machine learning."],
    "model": "bge-reranker-v2-m3-q4_0"
  }' | jq .
```

---

## llama-server 原生接口

### 健康检查

```bash
curl -s localhost:18790/v1/rerank/health | jq .
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
curl -s localhost:18790/v1/rerank/props | jq .
```

```json
{
  "default_generation_settings": {},
  "total_slots": 1,
  "model_path": "/home/liudecheng/.cache/spacemit-ai-gateway/rerank/models/bge-reranker-v2-m3-q4_0.gguf"
}
```

### Prometheus 指标

```bash
curl -s localhost:18790/v1/rerank/metrics
```

```
# HELP llamacpp:prompt_tokens_total Number of prompt tokens processed.
# TYPE llamacpp:prompt_tokens_total counter
llamacpp:prompt_tokens_total 135

# HELP llamacpp:tokens_predicted_total Number of generation tokens processed.
# TYPE llamacpp:tokens_predicted_total counter
llamacpp:tokens_predicted_total 0
```

---

## 接口覆盖测试

| 域       | 方法   | 路径                              | 状态 | 备注                          |
|----------|--------|-----------------------------------|------|-------------------------------|
| Rerank   | GET    | /v1/rerank/healthz                | PASS |                               |
| Rerank   | GET    | /v1/rerank/models                 | PASS |                               |
| Rerank   | POST   | /v1/rerank/models/register        | PASS |                               |
| Rerank   | POST   | /v1/rerank/models/load            | PASS |                               |
| Rerank   | POST   | /v1/rerank/models/unload          | PASS |                               |
| Rerank   | POST   | /v1/rerank/models/switch          | PASS |                               |
| Rerank   | POST   | /v1/rerank/models/deregister      | PASS |                               |
| Rerank   | POST   | /v1/rerank/rerank                 | PASS |                               |
| Rerank   | GET    | /v1/rerank/health                 | PASS |                               |
| Rerank   | GET    | /v1/rerank/props                  | PASS |                               |
| Rerank   | GET    | /v1/rerank/slots                  | PASS |                               |
| Rerank   | GET    | /v1/rerank/metrics                | PASS | Prometheus 格式               |
| Jira 兼容| POST   | /v1/rerank                        | PASS |                               |
