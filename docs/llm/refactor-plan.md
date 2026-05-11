# LLM 域重构规划

## 目标

将 `LLMService` 拆成两层，与 ASR/TTS/VAD 的架构对齐：

```
adapters/base.py       — LlmBackend ABC（warmup / shutdown / proxy）
adapters/llm_backend.py — LlmBackendImpl，管 llama-server 进程 + remote 转发
service.py             — LLMService(backends, default, config)，DB + 业务逻辑
adapters/__init__.py   — build_llm_backends 工厂
```

## 当前问题

`LLMService` 既是 backend（管进程）又是 service（管 DB），两层混在一起：
- `_adapters: dict[str, LlamaAdapter]` — 进程管理
- `_db` — SQLite 持久化
- `load/unload/switch` — 既操作进程又操作 DB

## 拆分方案

### adapters/llm_backend.py — LlmBackendImpl

职责：管理 llama-server 进程和 remote 转发，不碰 DB。

```python
class LlmBackendImpl(LlmBackend):
    backend_name = "llm"

    def __init__(self, config: LlmConfig): ...

    # 进程管理
    async def start_model(self, model_id: str, model_path: Path, extra_args: list[str]) -> None: ...
    async def stop_model(self, model_id: str) -> None: ...
    def is_model_running(self, model_id: str) -> bool: ...

    # 代理
    async def proxy(self, path: str, body: bytes, headers: dict, stream: bool): ...

    # 生命周期
    async def warmup(self) -> None: ...
    async def shutdown(self) -> None: ...
```

### service.py — LLMService

职责：DB 持久化、模型状态机、下载、业务逻辑。

```python
class LLMService:
    def __init__(
        self,
        backends: dict[str, LlmBackend],
        default: str,
        config: LlmConfig,
    ): ...

    @property
    def backend(self) -> LlmBackend:
        return self._backends[self._default]
```

### adapters/__init__.py — 工厂

```python
def build_llm_backends(config: LlmConfig) -> dict[str, LlmBackend]:
    name = config.backend or "llm"
    return {name: LlmBackendImpl(config=config)}
```

### lifespan.py — 对齐 VAD 格式

```python
llm_backends = build_llm_backends(settings.llm)
llm_default = settings.llm.backend
if not llm_default or llm_default not in llm_backends:
    llm_default = next(iter(llm_backends))
    logger.warning(...)

llm_service = LLMService(llm_backends, llm_default, config=settings.llm)
```

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `adapters/base.py` | 已有，补充 `proxy` 抽象方法 |
| `adapters/llm_backend.py` | 新建，从 `service.py` 提取进程管理逻辑 |
| `adapters/llama.py` | 保留，`LlmBackendImpl` 内部使用 |
| `adapters/remote.py` | 保留，`LlmBackendImpl` 内部使用 |
| `adapters/__init__.py` | 更新工厂，返回 `LlmBackendImpl` |
| `service.py` | 改签名，进程操作委托给 `backend` |

## 注意事项

- `service.py` 里 `_do_load` 直接 `new LlamaAdapter()`，拆后改为调 `backend.start_model()`
- `api.py` 通过 `request.app.state.llm_service` 取 service，不需要改
- `warmup` 在 `LlmBackendImpl` 实现，`LLMService` 的 `warmup` 改为先 `initialize` 再委托给 `backend.warmup()`
