"""Base model service lifecycle tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from spacemit_ai_gateway.app.settings import LlmConfig, LlmStorageConfig
from spacemit_ai_gateway.common.enums import ModelStatus
from spacemit_ai_gateway.common.base_service import BaseModelService


class _FailingWarmupAdapter:
    def is_running(self) -> bool:
        return True

    async def warmup(self) -> None:
        raise RuntimeError("warmup failed")


class _FakeLifecycleBackend:
    def __init__(self) -> None:
        self._remote_adapters = {}
        self.running: set[str] = set()
        self.stopped: list[str] = []
        self.adapter = _FailingWarmupAdapter()

    def is_model_running(self, model: str) -> bool:
        return model in self.running

    async def start_model(self, model: str, path: Path, args: list[str]) -> None:
        self.running.add(model)

    def get_adapter(self, model: str):
        if model in self.running:
            return self.adapter
        return None

    async def stop_model(self, model: str) -> None:
        self.stopped.append(model)
        self.running.discard(model)

    async def shutdown(self) -> None:
        self.running.clear()


class _LifecycleService(BaseModelService[_FakeLifecycleBackend, LlmConfig]):
    @property
    def adapter(self):
        return self._get_backend_impl().get_adapter(self._current_model or "")

    def _get_backend_impl(self) -> _FakeLifecycleBackend:
        return self._backends[self._default]


async def test_load_failure_stops_backend_and_restores_downloaded_status(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    model_file = models_dir / "warmup-fail.gguf"
    model_file.write_bytes(b"fake")
    backend = _FakeLifecycleBackend()
    service = _LifecycleService(
        {"fake": backend},
        "fake",
        LlmConfig(
            backend="warmup-fail",
            storage=LlmStorageConfig(
                models_dir=str(models_dir),
                db_path=str(tmp_path / "db.sqlite"),
            ),
            models=[{"id": "warmup-fail", "url": model_file.name}],
        ),
    )

    await service.initialize()
    try:
        with pytest.raises(RuntimeError, match="warmup failed"):
            await service.load("warmup-fail")

        progress = await service.get_download_progress("warmup-fail")
        assert progress["status"] == ModelStatus.DOWNLOADED
        assert backend.stopped == ["warmup-fail"]
        assert backend.running == set()
    finally:
        await service.shutdown()
