"""Unit tests for VLM model service."""


import pytest

from spacemit_ai_gateway.app.settings import VlmConfig, VlmStorageConfig
from spacemit_ai_gateway.domains.vlm.adapters import build_vlm_backends
from spacemit_ai_gateway.domains.vlm.service import VlmService


@pytest.mark.asyncio
async def test_vlm_remote_model_lifecycle(tmp_path):
    config = VlmConfig(
        backend=None,
        storage=VlmStorageConfig(
            base_dir=str(tmp_path / "cache"),
            models_dir=str(tmp_path / "models"),
            db_path=str(tmp_path / "vlm.sqlite"),
        ),
    )
    service = VlmService(build_vlm_backends(config), "vlm", config=config)
    await service.initialize()

    try:
        result = await service.register(
            "test-vlm-remote",
            source_type="remote",
            api_base_url="http://127.0.0.1:18080/v1",
            api_key="sk-test",
        )
        assert result == {"model": "test-vlm-remote", "status": "loaded"}

        await service.switch("test-vlm-remote")
        assert service.get_current_model() == "test-vlm-remote"
        assert service.get_current_source_type() == "remote"
        assert service.adapter is None

        info = await service.healthz()
        assert info["ready"] is True
        assert info["state"] == "ready"
    finally:
        await service.shutdown()
