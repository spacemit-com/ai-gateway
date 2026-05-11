### 2.4 LLM（`/v1/llm` 前缀）

路径相对 spacemit-ai-gateway 根 URL，前缀 `/v1/llm`，透传到 llama-server（默认 `http://127.0.0.1:8020`）。
| 属性 | GET | `/v1/llm/props` | 无 | 查看服务属性 |
| 属性 | POST | `/v1/llm/props` | 当前无明确字段 | 修改服务属性，需 `--props` |
| Slot | GET | `/v1/llm/slots` | `fail_on_no_slot` | 查看 slot 状态 |
| Slot | POST | `/v1/llm/slots/{id_slot}?action=save` | `filename` | 保存 prompt cache |
| Slot | POST | `/v1/llm/slots/{id_slot}?action=restore` | `filename` | 恢复 prompt cache |
| Slot | POST | `/v1/llm/slots/{id_slot}?action=erase` | 无 | 清空 prompt cache |
| 指标 | GET | `/v1/llm/metrics` | 无 | Prometheus 指标 |
| LoRA | GET | `/v1/llm/lora-adapters` | 无 | 查看适配器列表 |
| LoRA | POST | `/v1/llm/lora-adapters` | `[{id, scale}]` | 设置全局 LoRA scale |

---

### 2.5 Embed（`/v1/embed` 前缀）

路径相对 spacemit-ai-gateway 根 URL，前缀 `/v1/embed`，透传到 embed llama-server（启动时带 `--embedding` 标志）。

| 分类 | 方法 | 路径 | 主要参数 | 说明 |
|------|------|------|----------|------|
| 健康检查 | GET | `/v1/embed/healthz` | 无 | 服务健康状态 |
| 模型发现 | GET | `/v1/embed/models` | 无 | 模型信息 |
| Embedding | POST | `/v1/embed/embedding` | `content`, `embd_normalize` | 原生 embedding（单条） |
| Embedding | POST | `/v1/embed/embeddings` | `input`, `pooling` | 原生 embeddings，支持更多 pooling 类型 |
| Tokenize | POST | `/v1/embed/tokenize` | `content`, `add_special`, `parse_special` | 文本转 token |
| 指标 | GET | `/v1/embed/metrics` | 无 | Prometheus 指标 |

**Embed 兼容接口汇总**

| 兼容协议 | 方法 | 路径 | 主要参数 | 说明 |
|----------|------|------|----------|------|
| OpenAI | POST | `/v1/embeddings` | `model`, `input`, `encoding_format` | OpenAI 兼容 embeddings |

---

### 2.6 Rerank（`/v1/rerank` 前缀）

路径相对 spacemit-ai-gateway 根 URL，前缀 `/v1/rerank`，透传到 rerank llama-server（启动时带 `--reranking` 标志）。

| 分类 | 方法 | 路径 | 主要参数 | 说明 |
|------|------|------|----------|------|
| 健康检查 | GET | `/v1/rerank/healthz` | 无 | 服务健康状态 |
| 模型发现 | GET | `/v1/rerank/models` | 无 | 模型信息 |
| Rerank | POST | `/v1/rerank/rerank` | `query`, `documents`, `top_n` | 原生重排序 |
| Rerank | POST | `/v1/rerank/reranking` | `query`, `documents`, `top_n` | 原生重排序别名 |
| Tokenize | POST | `/v1/rerank/tokenize` | `content`, `add_special`, `parse_special` | 文本转 token |
| 指标 | GET | `/v1/rerank/metrics` | 无 | Prometheus 指标 |

**Rerank 兼容接口汇总**

| 兼容协议 | 方法 | 路径 | 主要参数 | 说明 |
|----------|------|------|----------|------|
| OpenAI | POST | `/v1/rerank` | `model`, `query`, `documents`, `top_n` | OpenAI 兼容重排序 |
| OpenAI | POST | `/v1/reranking` | `model`, `query`, `documents`, `top_n` | OpenAI 兼容重排序别名 |
