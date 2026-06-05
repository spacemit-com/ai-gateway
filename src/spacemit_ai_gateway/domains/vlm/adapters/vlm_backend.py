"""VlmBackendImpl — manages local llama-server and remote VLM adapters."""

from __future__ import annotations

import logging
from pathlib import Path

from ....app.settings import VlmConfig
from .base import VlmBackend
from .llama import VlmLlamaAdapter
from .remote import RemoteAdapter

logger = logging.getLogger(__name__)


class VlmBackendImpl(VlmBackend):
    backend_name = "vlm"

    def __init__(self, config: VlmConfig):
        self._config = config
        self._adapters: dict[str, VlmLlamaAdapter] = {}
        self._remote_adapters: dict[str, RemoteAdapter] = {}

    async def start_model(self, model_id: str, model_path: Path, extra_args: list[str]) -> None:
        """Start llama-server for a VLM model, health-check, then register adapter."""
        if model_id in self._adapters:
            await self.stop_model(model_id)
        adapter = VlmLlamaAdapter(host=self._config.host, default_args=self._config.default_args)
        try:
            adapter.start(model_path, extra_args=extra_args)
            ready = await adapter.health_check(timeout=120)
            if not ready:
                raise RuntimeError(f"VLM llama-server failed to start for model '{model_id}'")
        except Exception:
            adapter.stop()
            raise
        self._adapters[model_id] = adapter

    async def stop_model(self, model_id: str) -> None:
        adapter = self._adapters.pop(model_id, None)
        if adapter:
            adapter.stop()

    def is_model_running(self, model_id: str) -> bool:
        adapter = self._adapters.get(model_id)
        return adapter is not None and adapter.is_running()

    def get_adapter(self, model_id: str) -> VlmLlamaAdapter | None:
        return self._adapters.get(model_id)

    def register_remote(self, model_id: str, api_base_url: str, api_key: str = "") -> None:
        self._remote_adapters[model_id] = RemoteAdapter(api_base_url, api_key)

    def unregister_remote(self, model_id: str) -> None:
        self._remote_adapters.pop(model_id, None)

    async def proxy_for(self, model_id: str, source_type: str,
                        path: str, request_body: bytes, headers: dict, stream: bool = False):
        if source_type in ("remote", "local_url"):
            remote = self._remote_adapters.get(model_id)
            if remote:
                remote_path = path
                if remote.api_base_url.endswith("/v1") and path.startswith("/v1/"):
                    remote_path = path[3:]
                return await remote.proxy(remote_path, request_body, headers, stream)
        adapter = self._adapters.get(model_id)
        if not adapter:
            raise RuntimeError(f"Model '{model_id}' is not loaded")
        return await adapter.proxy(path, request_body, headers, stream)

    async def warmup(self) -> None:
        pass

    async def shutdown(self) -> None:
        for adapter in self._adapters.values():
            adapter.stop()
        self._adapters.clear()
        self._remote_adapters.clear()
