"""RerankBackendImpl — 管理 llama-server --reranking 进程（参考 Embed）。"""

from __future__ import annotations

import logging
from pathlib import Path

from ....app.settings import RerankConfig
from .base import RerankBackend
from .llama import LlamaRerankAdapter
from .remote import RemoteAdapter

logger = logging.getLogger(__name__)


class RerankBackendImpl(RerankBackend):
    backend_name = "rerank"

    def __init__(self, config: RerankConfig):
        self._config = config
        self._adapters: dict[str, LlamaRerankAdapter] = {}
        self._remote_adapters: dict[str, RemoteAdapter] = {}

    # ── 进程管理 ──────────────────────────────────────────────────────────────

    async def start_model(self, model_id: str, model_path: Path, extra_args: list[str]) -> None:
        """启动 llama-server --reranking，健康检查通过后注册 adapter。"""
        adapter = LlamaRerankAdapter(host=self._config.host, default_args=self._config.default_args)
        adapter.start(model_path, extra_args=extra_args)
        ready = await adapter.health_check(timeout=120)
        if not ready:
            adapter.stop()
            raise RuntimeError(f"llama-server --reranking failed to start for model '{model_id}'")
        self._adapters[model_id] = adapter

    async def stop_model(self, model_id: str) -> None:
        adapter = self._adapters.pop(model_id, None)
        if adapter:
            adapter.stop()

    def is_model_running(self, model_id: str) -> bool:
        adapter = self._adapters.get(model_id)
        return adapter is not None and adapter.is_running()

    def get_adapter(self, model_id: str) -> LlamaRerankAdapter | None:
        return self._adapters.get(model_id)

    def register_remote(self, model_id: str, api_base_url: str, api_key: str = "") -> None:
        self._remote_adapters[model_id] = RemoteAdapter(api_base_url, api_key)

    def unregister_remote(self, model_id: str) -> None:
        self._remote_adapters.pop(model_id, None)

    # ── 代理 ─────────────────────────────────────────────────────────────────

    async def proxy(self, path: str, request_body: bytes, headers: dict, stream: bool = False):
        raise NotImplementedError("Use proxy_for(model_id) instead")

    async def proxy_for(self, model_id: str, source_type: str,
                        path: str, request_body: bytes, headers: dict, stream: bool = False):
        if source_type == "remote":
            remote = self._remote_adapters.get(model_id)
            if not remote:
                raise RuntimeError(f"No remote adapter for model '{model_id}'")
            return await remote.proxy(path, request_body, headers, stream)
        adapter = self._adapters.get(model_id)
        if not adapter:
            raise RuntimeError(f"Model '{model_id}' is not loaded")
        return await adapter.proxy(path, request_body, headers, stream)

    # ── 生命周期 ──────────────────────────────────────────────────────────────

    async def warmup(self) -> None:
        pass  # service 层负责 warmup 当前活跃 adapter

    async def shutdown(self) -> None:
        for adapter in self._adapters.values():
            adapter.stop()
        self._adapters.clear()
        self._remote_adapters.clear()
