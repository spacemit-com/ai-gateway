"""TTS service 单元测试。"""

from __future__ import annotations

import pytest

from spacemit_ai_gateway.app.settings import TtsConfig
from spacemit_ai_gateway.common.errors import InvalidSessionError, ModelUnknown
from spacemit_ai_gateway.common.sessions import SessionStore
from spacemit_ai_gateway.domains.tts.schemas import StreamSessionRequest, SynthesizeRequest
from spacemit_ai_gateway.domains.tts.service import TtsService


async def test_synthesize_returns_audio(tts_service):
    audio, ctype, meta = await tts_service.synthesize(
        SynthesizeRequest(text="你好", response_format="wav")
    )
    assert isinstance(audio, (bytes, bytearray))
    assert len(audio) > 0
    assert "wav" in ctype or ctype.startswith("audio/")
    assert meta["sample_rate"] == 22050


async def test_create_stream_session_and_open(tts_service):
    ss = await tts_service.create_stream_session(
        StreamSessionRequest(voice_id="default", response_format="pcm")
    )
    assert ss.session_id
    stream = await tts_service.open_stream(
        session_id=ss.session_id, voice_id="default", response_format="pcm"
    )
    assert stream is not None


async def test_open_stream_without_session_raises(tts_service):
    with pytest.raises(InvalidSessionError):
        await tts_service.open_stream(
            session_id=None, voice_id=None, response_format="pcm"
        )


async def test_healthz_ready(tts_service):
    h = await tts_service.healthz()
    assert h["ready"] is True
    assert h["backend"] == "fake-tts"


def test_get_models_respects_configured_backends():
    service = TtsService(
        {},
        "matcha_zh_en",
        SessionStore(ttl_seconds=60, namespace="tts-allow-list"),
        config=TtsConfig(backend="matcha_zh_en", backends=["matcha_zh_en"]),
    )

    assert [model.id for model in service.get_models()] == ["matcha_zh_en"]


async def test_load_rejects_unconfigured_backend():
    service = TtsService(
        {},
        "matcha_zh_en",
        SessionStore(ttl_seconds=60, namespace="tts-allow-list"),
        config=TtsConfig(backend="matcha_zh_en", backends=["matcha_zh_en"]),
    )

    with pytest.raises(ModelUnknown) as exc_info:
        await service.load_model("kokoro")

    assert exc_info.value.details == {"available": ["matcha_zh_en"]}
