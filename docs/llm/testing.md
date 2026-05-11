# SpacemiT AI Gateway LLM 测试记录

> 测试环境：Linux x86_64，Python 3.x，服务监听 `localhost:18790`
> 默认模型：`qwen3-0.6b-q4_0`（preset，启动时自动下载并加载）

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
./scripts/llm/clean.sh db      # 删除数据库
./scripts/llm/clean.sh models  # 删除所有模型文件
./scripts/llm/clean.sh kill    # 杀掉 18790 端口进程
./scripts/llm/clean.sh all     # 全部清理
```

### 模型来源说明

| source_type  | 说明                                        |
|--------------|---------------------------------------------|
| `local_path` | 本地 GGUF 文件，直接加载                    |
| `local_url`  | 远程 GGUF，下载后缓存到本地再启动           |
| `remote`     | 透传到外部 OpenAI 兼容 API，不启动本地进程  |

---

## 自动下载与加载

服务启动时，若 `configs/base.yaml` 中配置了 `llm.backend`，会自动：

1. 检查模型文件是否已在 `~/.cache/models/llm/` 中
2. 文件存在 → 直接加载
3. 文件不存在 → 后台下载，完成后自动加载（不阻塞服务启动）

启动日志示例：

```
[autoload] default_model 'qwen3-0.6b-q4_0' not downloaded, starting background download
[autoload] download complete for 'qwen3-0.6b-q4_0', loading...
[autoload] 'qwen3-0.6b-q4_0' loaded and active
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
    "asr":    { "ready": true,  "state": "ready",        "backend": "sensevoice (mock)" },
    "tts":    { "ready": true,  "state": "ready",        "backend": "matcha_zh (mock)"  },
    "vad":    { "ready": true,  "state": "ready",        "backend": "silero (mock)"     },
    "llm":    { "ready": true,  "state": "ready",        "backend": "qwen3-0.6b-q4_0"  },
    "vision": { "ready": false, "state": "uninitialized","backend": "unknown"           }
  }
}
```

> `status: degraded` 是因为 vision 未初始化，与 LLM 无关。

---

## LLM 健康检查

```bash
curl -s localhost:18790/v1/llm/healthz | jq .
```

模型已加载：

```json
{ "status": "ready", "model": "qwen3-0.6b-q4_0" }
```

无模型加载时：

```json
{ "status": "failed", "model": null }
```

---

## 模型管理

### 列出模型

```bash
curl -s localhost:18790/v1/llm/models | jq .
```

```json
[
  {
    "id": "qwen2.5-0.5b-instruct-q4_0",
    "source_type": "local_url",
    "url": "https://archive.spacemit.com/spacemit-ai/model_zoo/llm/qwen2.5-0.5b-instruct-q4_0.gguf",
    "local_path": null,
    "status": "available",
    "is_preset": 1,
    "download_progress": 0.0
  },
  {
    "id": "qwen3-0.6b-q4_0",
    "source_type": "local_url",
    "url": "https://archive.spacemit.com/spacemit-ai/model_zoo/llm/Qwen3-0.6B-Q4_0.gguf",
    "local_path": "/home/liudecheng/.cache/spacemit-ai-gateway/llm/models/qwen3-0.6b-q4_0.gguf",
    "status": "loaded",
    "is_preset": 1,
    "download_progress": 1.0
  },
  {
    "id": "qwen3.5-2b-q4_0",
    "source_type": "local_url",
    "url": "https://archive.spacemit.com/spacemit-ai/model_zoo/llm/Qwen3.5-2B-Q4_0.gguf",
    "local_path": null,
    "status": "available",
    "is_preset": 1,
    "download_progress": 0.0
  }
]
```

### 注册模型（local_path）

```bash
curl -s -X POST localhost:18790/v1/llm/models/register \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "test-local",
    "source_type": "local_path",
    "local_path": "/path/to/model.gguf"
  }' | jq .
```

```json
{ "model": "test-local", "status": "downloaded" }
```

### 注册模型（remote）

```bash
curl -s -X POST localhost:18790/v1/llm/models/register \
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
curl -s -X POST localhost:18790/v1/llm/models/load \
  -H 'Content-Type: application/json' \
  -d '{"model": "qwen3-0.6b-q4_0"}' | jq .
```

```json
{ "model": "qwen3-0.6b-q4_0", "status": "loaded" }
```

附加 llama-server 参数：

```bash
curl -s -X POST localhost:18790/v1/llm/models/load \
  -H 'Content-Type: application/json' \
  -d '{"model": "qwen3-0.6b-q4_0", "extra_args": ["--ctx-size", "8192", "--threads", "4"]}' | jq .
```

### 卸载模型

```bash
curl -s -X POST localhost:18790/v1/llm/models/unload \
  -H 'Content-Type: application/json' \
  -d '{"model": "qwen3-0.6b-q4_0"}' | jq .
```

```json
{ "model": "qwen3-0.6b-q4_0", "status": "unloaded" }
```

### 切换模型

```bash
curl -s -X POST localhost:18790/v1/llm/models/switch \
  -H 'Content-Type: application/json' \
  -d '{"model": "qwen3-0.6b-q4_0"}' | jq .
```

```json
{ "model": "qwen3-0.6b-q4_0", "status": "loaded" }
```

### 注销模型

```bash
curl -s -X POST localhost:18790/v1/llm/models/deregister \
  -H 'Content-Type: application/json' \
  -d '{"model": "test-local"}' | jq .
```

```json
{ "model": "test-local", "status": "deregistered" }
```

---

## 模型下载（local_url）

### 注册并触发下载

```bash
curl -s -X POST localhost:18790/v1/llm/models/register \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "test-dl",
    "source_type": "local_url",
    "url": "https://archive.spacemit.com/spacemit-ai/model_zoo/llm/qwen2.5-0.5b-instruct-q4_0.gguf"
  }' | jq .
```

```json
{ "model": "test-dl", "status": "available" }
```

```bash
curl -s -X POST localhost:18790/v1/llm/models/test-dl/download | jq .
```

```json
{ "model": "test-dl", "status": "downloading" }
```

### 查询下载进度

```bash
curl -s localhost:18790/v1/llm/models/test-dl/download | jq .
```

下载中：

```json
{ "model": "test-dl", "status": "downloading", "progress": 0.066 }
```

下载完成：

```json
{ "model": "test-dl", "status": "downloaded", "progress": 1.0 }
```

### 取消下载

```bash
curl -s -X DELETE localhost:18790/v1/llm/models/test-dl/download | jq .
```

```json
{ "model": "test-dl", "status": "available" }
```

---

## 推理接口

### chat/completions（非流式）

```bash
curl -s -X POST localhost:18790/v1/llm/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen3-0.6b-q4_0",
    "messages": [{"role": "user", "content": "你好，一句话介绍自己"}],
    "stream": false,
    "max_tokens": 64
  }' | jq .
```

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1776819880,
  "model": "qwen3-0.6b-q4_0.gguf",
  "choices": [{
    "index": 0,
    "message": { "role": "assistant", "content": "", "reasoning_content": "..." },
    "finish_reason": "length"
  }],
  "usage": { "prompt_tokens": 13, "completion_tokens": 64, "total_tokens": 77 }
}
```

### chat/completions（流式）

```bash
curl -s -X POST localhost:18790/v1/llm/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen3-0.6b-q4_0",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true,
    "max_tokens": 64
  }'
```

返回 SSE 流：`data: {"choices":[{"delta":{"content":"..."}}],...}`

### completions（OpenAI text completion）

```bash
curl -s -X POST localhost:18790/v1/llm/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-0.6b-q4_0","prompt":"Once upon a time","stream":false,"max_tokens":16}' | jq .
```

```json
{
  "object": "text_completion",
  "choices": [{ "text": ", a man was walking past the store.", "index": 0, "finish_reason": "length" }],
  "usage": { "prompt_tokens": 4, "completion_tokens": 16, "total_tokens": 20 }
}
```

### completion（llama-server 原生）

```bash
curl -s -X POST localhost:18790/v1/llm/completion \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Once upon a time","n_predict":16,"stream":false}' | jq .
```

```json
{
  "content": ", a boy was given a problem like this: ...",
  "tokens_predicted": 16,
  "tokens_evaluated": 4,
  "stop": true
}
```

### responses（OpenAI Responses API）

```bash
curl -s -X POST localhost:18790/v1/llm/responses \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-0.6b-q4_0","input":"你好","stream":false}' | jq .
```

```json
{
  "id": "resp_xxx",
  "object": "response",
  "model": "qwen3-0.6b-q4_0.gguf",
  "output": [{ "type": "message", "role": "assistant", "content": [...] }]
}
```

### infill（代码填充）

```bash
curl -s -X POST localhost:18790/v1/llm/infill \
  -H 'Content-Type: application/json' \
  -d '{"input_prefix":"def hello(","input_suffix"):","prompt":""}' | jq .
```

### tokenize / detokenize

```bash
curl -s -X POST localhost:18790/v1/llm/tokenize \
  -H 'Content-Type: application/json' \
  -d '{"content": "你好世界", "add_special": true}' | jq .
```

```json
{ "tokens": [108386, 99489] }
```

```bash
curl -s -X POST localhost:18790/v1/llm/detokenize \
  -H 'Content-Type: application/json' \
  -d '{"tokens": [9906, 1917]}' | jq .
```

```json
{ "content": " bright action" }
```

### apply-template

```bash
curl -s -X POST localhost:18790/v1/llm/apply-template \
  -H 'Content-Type: application/json' \
  -d '{"messages": [{"role": "user", "content": "你好"}]}' | jq .
```

```json
{ "prompt": "<|im_start|>user\n你好<|im_end|>\n<|im_start|>assistant\n" }
```

### props（GET）

```bash
curl -s localhost:18790/v1/llm/props | jq .default_generation_settings.params.temperature
```

```
0.800000011920929
```

> POST /v1/llm/props 需要启动时加 `--props` 参数，否则返回 501。

### slots（GET）

```bash
curl -s localhost:18790/v1/llm/slots | jq '[.[].id_slot]'
```

> POST /v1/llm/slots/{id_slot} 需要启动时加 `--slot-save-path` 参数，否则返回 501。

### lora-adapters

```bash
curl -s localhost:18790/v1/llm/lora-adapters | jq .
# []

curl -s -X POST localhost:18790/v1/llm/lora-adapters \
  -H 'Content-Type: application/json' \
  -d '[]' | jq .
# { "success": true }
```

### metrics（Prometheus）

```bash
curl -s localhost:18790/v1/llm/metrics | head -5
```

```
# HELP llamacpp:prompt_tokens_total Number of prompt tokens processed.
# TYPE llamacpp:prompt_tokens_total counter
llamacpp:prompt_tokens_total 14
```

---

## OpenAI 兼容接口（根路径）

```bash
# GET /v1/models
curl -s localhost:18790/v1/models | jq .
```

```json
{ "object": "list", "data": [{ "id": "qwen3-0.6b-q4_0", "object": "model", "owned_by": "spacemit-ai-gateway" }] }
```

```bash
# GET /models
curl -s localhost:18790/models | jq .

# POST /v1/chat/completions
curl -s -X POST localhost:18790/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-0.6b-q4_0","messages":[{"role":"user","content":"1+1=?"}],"stream":false,"max_tokens":8}' | jq .

# POST /chat/completions
curl -s -X POST localhost:18790/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-0.6b-q4_0","messages":[{"role":"user","content":"hi"}],"stream":false,"max_tokens":8}' | jq .

# POST /v1/completions
curl -s -X POST localhost:18790/v1/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-0.6b-q4_0","prompt":"hi","stream":false,"max_tokens":8}' | jq .

# POST /completions
curl -s -X POST localhost:18790/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-0.6b-q4_0","prompt":"hi","stream":false,"max_tokens":8}' | jq .

# POST /v1/responses
curl -s -X POST localhost:18790/v1/responses \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-0.6b-q4_0","input":"hi","stream":false}' | jq .
```

---

## Anthropic 兼容接口

```bash
# POST /v1/messages
curl -s -X POST localhost:18790/v1/messages \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-0.6b-q4_0","messages":[{"role":"user","content":"hi"}],"max_tokens":16}' | jq .
```

```json
{
  "id": "chatcmpl-xxx",
  "type": "message",
  "role": "assistant",
  "content": [{ "type": "thinking", "thinking": "..." }],
  "model": "qwen3-0.6b-q4_0.gguf",
  "stop_reason": "max_tokens",
  "usage": { "input_tokens": 9, "output_tokens": 16 }
}
```

```bash
# POST /v1/messages/count_tokens
curl -s -X POST localhost:18790/v1/messages/count_tokens \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-0.6b-q4_0","messages":[{"role":"user","content":"hi"}]}' | jq .
```

```json
{ "input_tokens": 9 }
```

---

## Ollama 兼容接口

```bash
# GET /v1/llm/api/tags
curl -s localhost:18790/v1/llm/api/tags | jq .
```

```json
{ "models": [{ "name": "qwen3-0.6b-q4_0", "model": "qwen3-0.6b-q4_0" }] }
```

```bash
# POST /v1/llm/api/chat
curl -s -X POST localhost:18790/v1/llm/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-0.6b-q4_0","messages":[{"role":"user","content":"hi"}],"stream":false}' | jq .
```

```json
{
  "model": "qwen3-0.6b-q4_0",
  "message": { "role": "assistant", "content": "Hello! How can I assist you today?" },
  "done": true,
  "done_reason": "stop",
  "prompt_eval_count": 9,
  "eval_count": 95
}
```

```bash
# POST /v1/llm/api/generate
curl -s -X POST localhost:18790/v1/llm/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-0.6b-q4_0","prompt":"hi","stream":false}' | jq .
```

```json
{
  "model": "qwen3-0.6b-q4_0",
  "response": "",
  "done": true,
  "done_reason": "stop",
  "prompt_eval_count": 0,
  "eval_count": 0
}
```

```bash
# POST /v1/llm/api/show
curl -s -X POST localhost:18790/v1/llm/api/show \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-0.6b-q4_0"}' | jq .model_info
```

```json
{ "llama.context_length": 4096 }
```

---

## 接口测试汇总

| 域       | 方法   | 路径                              | 状态 | 备注                          |
|----------|--------|-----------------------------------|------|-------------------------------|
| 系统     | GET    | /healthz                          | PASS |                               |
| LLM      | GET    | /v1/llm/healthz                   | PASS |                               |
| LLM      | GET    | /v1/llm/models                    | PASS |                               |
| LLM      | POST   | /v1/llm/models/register           | PASS | local_path / local_url / remote |
| LLM      | POST   | /v1/llm/models/deregister         | PASS |                               |
| LLM      | POST   | /v1/llm/models/load               | PASS |                               |
| LLM      | POST   | /v1/llm/models/unload             | PASS |                               |
| LLM      | POST   | /v1/llm/models/switch             | PASS |                               |
| LLM      | POST   | /v1/llm/models/{model}/download   | PASS |                               |
| LLM      | DELETE | /v1/llm/models/{model}/download   | PASS |                               |
| LLM      | GET    | /v1/llm/models/{model}/download   | PASS |                               |
| LLM      | POST   | /v1/llm/chat/completions          | PASS | 流式 / 非流式                 |
| LLM      | POST   | /v1/llm/completions               | PASS |                               |
| LLM      | POST   | /v1/llm/completion                | PASS | llama-server 原生             |
| LLM      | POST   | /v1/llm/responses                 | PASS |                               |
| LLM      | POST   | /v1/llm/infill                    | PASS |                               |
| LLM      | POST   | /v1/llm/tokenize                  | PASS |                               |
| LLM      | POST   | /v1/llm/detokenize                | PASS |                               |
| LLM      | POST   | /v1/llm/apply-template            | PASS |                               |
| LLM      | GET    | /v1/llm/props                     | PASS |                               |
| LLM      | POST   | /v1/llm/props                     | PASS | 需 `--props` 参数，否则 501   |
| LLM      | GET    | /v1/llm/slots                     | PASS |                               |
| LLM      | POST   | /v1/llm/slots/{id_slot}           | PASS | 需 `--slot-save-path`，否则 501 |
| LLM      | GET    | /v1/llm/metrics                   | PASS | Prometheus 格式               |
| LLM      | GET    | /v1/llm/lora-adapters             | PASS |                               |
| LLM      | POST   | /v1/llm/lora-adapters             | PASS |                               |
| LLM      | GET    | /v1/llm/api/tags                  | PASS | Ollama                        |
| LLM      | POST   | /v1/llm/api/chat                  | PASS | Ollama                        |
| LLM      | POST   | /v1/llm/api/generate              | PASS | Ollama                        |
| LLM      | POST   | /v1/llm/api/show                  | PASS | Ollama                        |
| OAI 兼容 | GET    | /v1/models                        | PASS |                               |
| OAI 兼容 | GET    | /models                           | PASS |                               |
| OAI 兼容 | POST   | /v1/chat/completions              | PASS |                               |
| OAI 兼容 | POST   | /chat/completions                 | PASS |                               |
| OAI 兼容 | POST   | /v1/completions                   | PASS |                               |
| OAI 兼容 | POST   | /completions                      | PASS |                               |
| OAI 兼容 | POST   | /v1/responses                     | PASS |                               |
| Anthropic| POST   | /v1/messages                      | PASS |                               |
| Anthropic| POST   | /v1/messages/count_tokens         | PASS |                               |
