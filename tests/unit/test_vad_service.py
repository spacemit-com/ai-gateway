"""VAD service 单元测试。"""

from __future__ import annotations

import pytest

from spacemit_ai_gateway.app.settings import VadConfig
from spacemit_ai_gateway.common.errors import ModelUnknown
from spacemit_ai_gateway.domains.vad.service import VadService


async def test_analyze(vad_service):
    resp = await vad_service.analyze(b"\x00" * 3200, sample_rate=16000)
    assert resp.is_speech is True
    assert resp.probability >= 0.5


async def test_segment(vad_service):
    resp = await vad_service.segment(b"\x00" * 3200, sample_rate=16000)
    assert resp.duration_ms > 0
    assert len(resp.segments) == 1


async def test_params(vad_service):
    p = vad_service.get_params()
    assert p.sample_rate == 16000
    assert 0.0 <= p.trigger_threshold <= 1.0


async def test_healthz_ready(vad_service):
    h = await vad_service.healthz()
    assert h["ready"] is True
    assert h["backend"] == "fake-vad"


def test_get_models_respects_configured_backends():
    service = VadService(
        {},
        "silero",
        config=VadConfig(backend="silero", backends=["silero"]),
    )

    assert [model.id for model in service.get_models()] == ["silero"]


async def test_load_rejects_unconfigured_backend():
    service = VadService(
        {},
        "silero",
        config=VadConfig(backend="silero", backends=["silero"]),
    )

    with pytest.raises(ModelUnknown) as exc_info:
        await service.load_model("unknown-vad")

    assert exc_info.value.details == {"available": ["silero"]}
