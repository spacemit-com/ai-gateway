# Rerank Domain 实现文档

## 概述

Rerank domain 提供文本重排序（Text Rerankding）服务，完全参考 LLM domain 的架构设计。支持本地 GGUF 模型和远程 API 代理，兼容 OpenAI Rerankdings API。

## 架构设计

### 目录结构

```
src/spacemit_ai_gateway/domains/rerank/
├── __init__.py
├── adapters/
│   ├── __init__.py          # 工厂函数 build_rerank_backends
│   ├── base.py              # RerankBackend ABC
│   ├── rerank_backend.py     # RerankBackendImpl（管理进程）
│   ├── llama.py             # LlamaRerankAdapter（llama-server --rerankding）
│   └── remote.py            # RemoteAdapter（远程 API）
├── api.py                   # FastAPI 路由（/v1/rerank/*）
├── schemas.py               # Pydantic 模型
└── service.py               # RerankService（业务逻辑 + DB）
```

### 核心组件

#### 1. RerankBackend (adapters/base.py)

抽象基类，定义 backend 契约：

```python
class RerankBackend(ABC):
    @property
    @abstractmethod
    def backend_name(self) -> str: ...

    @abstractmethod
    async def proxy(self, path: str, request_body: bytes, headers: dict, stream: bool = False): ...

    async def warmup(self) -> None: ...
    async def shutdown(self) -> None: ...
```

#### 2. LlamaRerankAdapter (adapters/llama.py)

管理单个 `llama-server --rerankding` 进程：

- 启动参数：`llama-server -m <model> --port <port> --host <host> --rerankding`
- 端口管理：使用 `port_pool` 自动分配端口（18800-18900）
- 健康检查：轮询 `/health` 端点直到 `status=ok`
- Warmup：发送最小 rerankding 请求触发模型加载
- 代理：透传请求到 llama-server，返回 httpx 响应

#### 3. RerankBackendImpl (adapters/rerank_backend.py)

管理多个 rerankding 模型进程：

- `start_model(model_id, model_path, extra_args)` - 启动模型进程
- `stop_model(model_id)` - 停止模型进程
- `is_model_running(model_id)` - 检查模型是否运行
- `get_adapter(model_id)` - 获取模型适配器
- `register_remote(model_id, api_base_url, api_key)` - 注册远程模型
- `proxy_for(model_id, source_type, path, body, headers, stream)` - 代理请求

#### 4. RerankService (service.py)

业务逻辑和模型生命周期管理：

**模型状态机**：
```
available → downloading → downloaded → loading → loaded
```

**核心方法**：
- `initialize()` - 初始化 SQLite DB，同步预置模型，自动加载默认模型
- `list_models()` - 列出所有模型及状态
- `register(model, source_type, url, local_path, api_base_url, api_key)` - 注册模型
- `deregister(model)` - 注销模型
- `download(model)` - 后台下载模型（支持进度查询和取消）
- `load(model, extra_args)` - 加载模型（启动 llama-server 进程）
- `unload(model)` - 卸载模型（停止进程）
- `switch(model)` - 切换活跃模型
- `proxy(path, request_body, headers, stream)` - 代理推理请求
- `_resolve_model(request_body)` - 从请求体解析模型，自动加载

**数据库表结构**：
```sql
CREATE TABLE models (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL DEFAULT 'local_url',  -- local_url | local_path | remote
    url TEXT,
    local_path TEXT,
    api_base_url TEXT,
    api_key TEXT,
    status TEXT NOT NULL DEFAULT 'available',
    is_preset INTEGER NOT NULL DEFAULT 0,
    download_progress REAL DEFAULT 0
)
```

#### 5. API 路由 (api.py)

**模型管理接口**：
- `GET /v1/rerank/models` - 列出所有模型
- `POST /v1/rerank/models/register` - 注册模型
- `POST /v1/rerank/models/deregister` - 注销模型
- `POST /v1/rerank/models/load` - 加载模型
- `POST /v1/rerank/models/unload` - 卸载模型
- `POST /v1/rerank/models/switch` - 切换活跃模型

**下载管理接口**：
- `POST /v1/rerank/models/{model}/download` - 开始下载
- `GET /v1/rerank/models/{model}/download` - 查询下载进度
- `DELETE /v1/rerank/models/{model}/download` - 取消下载

**推理接口**：
- `POST /v1/rerank/*` - 透传所有 llama-server rerankding 端点
- `GET /v1/rerank/healthz` - 健康检查

**兼容接口**：
- `POST /v1/rerankdings` - OpenAI 兼容接口

## 配置

### settings.py

```python
class RerankStorageConfig(BaseModel):
    base_dir: str = "~/.cache/spacemit-ai-gateway/rerank"
    models_dir: str = "~/.cache/models/rerank"
    db_path: str = "~/.cache/spacemit-ai-gateway/rerank/db.sqlite"

class RerankConfig(BaseModel):
    host: str = "127.0.0.1"
    default_args: list[str] = ["--rerankding", "--threads", "8"]
    backend: Optional[str] = None
    backends: Optional[list[str]] = None
    port_pool: PortPoolConfig = Field(default_factory=PortPoolConfig)
    storage: RerankStorageConfig = Field(default_factory=RerankStorageConfig)
    models: list[dict[str, Any]] = Field(default_factory=list)
```

### base.yaml

```yaml
rerank:
  backend: null                      # 默认后端（可选）
  default_args: ["--rerankding", "--threads", "8", "--metrics"]
  port_pool:
    start: 18800
    end: 18900
  storage:
    base_dir: "~/.cache/spacemit-ai-gateway/rerank"
    models_dir: "~/.cache/models/rerank"
    db_path: "~/.cache/spacemit-ai-gateway/rerank/db.sqlite"
  models:
    - id: bge-small-zh-v1.5
      url: https://example.com/bge-small-zh-v1.5.gguf
```

## 使用示例

### 1. 注册模型

**本地 URL 模型**（需要下载）：
```bash
curl -X POST http://localhost:18790/v1/rerank/models/register \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "model": "bge-small-zh",
    "source_type": "local_url",
    "url": "https://example.com/bge-small-zh.gguf"
  }'
```

**本地路径模型**（已下载）：
```bash
curl -X POST http://localhost:18790/v1/rerank/models/register \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "model": "bge-small-zh",
    "source_type": "local_path",
    "local_path": "/path/to/bge-small-zh.gguf"
  }'
```

**远程 API 模型**：
```bash
curl -X POST http://localhost:18790/v1/rerank/models/register \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "model": "openai-rerank",
    "source_type": "remote",
    "api_base_url": "https://api.openai.com/v1",
    "api_key": "sk-..."
  }'
```

### 2. 下载模型

```bash
# 开始下载
curl -X POST http://localhost:18790/v1/rerank/models/bge-small-zh/download \
  -H "X-API-Key: your-api-key"

# 查询下载进度
curl http://localhost:18790/v1/rerank/models/bge-small-zh/download

# 取消下载
curl -X DELETE http://localhost:18790/v1/rerank/models/bge-small-zh/download \
  -H "X-API-Key: your-api-key"
```

### 3. 加载模型

```bash
curl -X POST http://localhost:18790/v1/rerank/models/load \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "model": "bge-small-zh",
    "extra_args": ["--ctx-size", "512"]
  }'
```

### 4. 生成 Rerankding

**OpenAI 兼容接口**：
```bash
curl -X POST http://localhost:18790/v1/rerankdings \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "model": "bge-small-zh",
    "input": "你好世界"
  }'
```

**批量输入**：
```bash
curl -X POST http://localhost:18790/v1/rerankdings \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "model": "bge-small-zh",
    "input": ["你好世界", "Hello World", "Bonjour le monde"]
  }'
```

### 5. 模型管理

**列出所有模型**：
```bash
curl http://localhost:18790/v1/rerank/models
```

**切换活跃模型**：
```bash
curl -X POST http://localhost:18790/v1/rerank/models/switch \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"model": "bge-large-zh"}'
```

**卸载模型**：
```bash
curl -X POST http://localhost:18790/v1/rerank/models/unload \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"model": "bge-small-zh"}'
```

**注销模型**：
```bash
curl -X POST http://localhost:18790/v1/rerank/models/deregister \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"model": "bge-small-zh"}'
```

## 与 LLM Domain 的对应关系

| LLM | Rerank | 说明 |
|-----|-------|------|
| `LlmBackend` | `RerankBackend` | Backend ABC |
| `LlmBackendImpl` | `RerankBackendImpl` | Backend 实现 |
| `LlamaAdapter` | `LlamaRerankAdapter` | llama-server 适配器 |
| `LLMService` | `RerankService` | 服务层 |
| `LlmConfig` | `RerankConfig` | 配置 |
| `llm_service` | `rerank_service` | app.state 注册名 |
| `/v1/llm/*` | `/v1/rerank/*` | API 前缀 |
| `--ctx-size 4096` | `--rerankding` | llama-server 启动参数 |
| `/v1/chat/completions` | `/v1/rerankdings` | OpenAI 兼容接口 |

## 自动加载机制

### 1. 启动时自动加载

如果配置了 `rerank.backend`，服务启动时会自动加载该模型：

```yaml
rerank:
  backend: "bge-small-zh"  # 启动时自动加载
```

### 2. 请求时自动加载

如果请求体中指定的模型未加载，`RerankService._resolve_model()` 会自动加载：

```bash
# 即使 bge-large-zh 未加载，也会自动加载后执行
curl -X POST http://localhost:18790/v1/rerankdings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "bge-large-zh",
    "input": "自动加载测试"
  }'
```

### 3. 并发保护

使用 `asyncio.Event` 防止同一模型被并发加载多次。

## 错误处理

### 常见错误

**模型未找到**：
```json
{
  "error": "Model 'xxx' not found"
}
```

**模型未下载**：
```json
{
  "error": "Model 'xxx' is not downloaded (status: available)"
}
```

**模型已在下载**：
```json
{
  "error": "Model 'xxx' is already downloading"
}
```

**预置模型无法注销**：
```json
{
  "error": "Model 'xxx' is a preset model and cannot be unregistered"
}
```

## 性能优化

### 1. 端口池复用

Rerank 和 LLM 共享端口池（18800-18900），避免端口冲突。

### 2. 进程管理

- 每个模型独立进程，互不影响
- 支持多模型并发服务
- 自动健康检查和重启

### 3. 下载优化

- 后台异步下载，不阻塞服务
- 支持断点续传（通过 temp 文件）
- 实时进度查询

### 4. Warmup

- 启动后自动 warmup，触发模型加载
- 减少首次推理延迟

## 监控和运维

### 健康检查

```bash
curl http://localhost:18790/v1/rerank/healthz
```

响应：
```json
{
  "status": "ready",
  "model": "bge-small-zh"
}
```

### Prometheus 指标

如果启动时添加 `--metrics` 参数，可通过以下端点获取指标：

```bash
curl http://localhost:18790/v1/rerank/metrics
```

## 开发指南

### 添加新的 Rerankding 模型

1. 在 `configs/base.yaml` 中添加模型配置：
```yaml
rerank:
  models:
    - id: your-model-name
      url: https://example.com/your-model.gguf
```

2. 重启服务，模型会自动同步到数据库

3. 下载并加载模型：
```bash
curl -X POST http://localhost:18790/v1/rerank/models/your-model-name/download
curl -X POST http://localhost:18790/v1/rerank/models/load -d '{"model": "your-model-name"}'
```

### 扩展 Backend

如果需要支持其他 rerankding 引擎（如 sentence-transformers），可以：

1. 创建新的 adapter 类继承 `RerankBackend`
2. 在 `build_rerank_backends()` 中注册
3. 更新配置支持新的 backend 类型

## 测试

### 单元测试

```bash
pytest tests/domains/rerank/ -v
```

### 集成测试

```bash
# 启动服务
python -m spacemit_ai_gateway.app.main

# 运行集成测试
pytest tests/integration/test_rerank.py -v
```

## 故障排查

### 模型加载失败

1. 检查模型文件是否存在：
```bash
ls ~/.cache/models/rerank/
```

2. 检查 llama-server 日志（如果有）

3. 验证模型格式是否为 GGUF

### 端口冲突

如果端口池耗尽，调整配置：
```yaml
rerank:
  port_pool:
    start: 19000
    end: 19100
```

### 下载失败

1. 检查网络连接
2. 验证 URL 是否可访问
3. 检查磁盘空间

## 参考资料

- [llama.cpp](https://github.com/ggerganov/llama.cpp)
- [OpenAI Rerankdings API](https://platform.openai.com/docs/api-reference/rerankdings)
- [GGUF Format](https://github.com/ggerganov/ggml/blob/master/docs/gguf.md)
