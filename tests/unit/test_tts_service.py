"""TTS service 单元测试。"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from spacemit_ai_gateway.app.settings import TtsConfig
from spacemit_ai_gateway.common.errors import InvalidSessionError, ModelUnknown
from spacemit_ai_gateway.common.ready_state import BackendReadyState
from spacemit_ai_gateway.common.schemas import ModelInfo, VoiceInfo
from spacemit_ai_gateway.common.sessions import SessionStore
from spacemit_ai_gateway.domains.tts.adapters.base import TtsBackend, TtsResult
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


class _BlockingTtsBackend(TtsBackend):
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.shutdown_called = False
        self.engine_lock = asyncio.Lock()

    @property
    def backend_name(self) -> str:
        return "blocking-tts"

    @property
    def sample_rate(self) -> int:
        return 22050

    @property
    def state(self) -> BackendReadyState:
        return BackendReadyState.READY

    async def synthesize(self, text, voice_id, speed, pitch, volume) -> TtsResult:
        async with self.engine_lock:
            self.started.set()
            await self.release.wait()
            return TtsResult(
                audio=np.zeros(22050, dtype=np.int16),
                sample_rate=22050,
                duration_ms=1000.0,
                processing_ms=2.0,
                rtf=0.002,
            )

    async def open_stream(self, voice_id, speed):
        raise NotImplementedError

    def get_voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(id="default", name="Blocking", language="zh")]

    def get_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="blocking",
                name="Blocking TTS",
                capabilities=["tts"],
                languages=["zh"],
            )
        ]

    async def shutdown(self) -> None:
        async with self.engine_lock:
            self.shutdown_called = True


class _ConcurrentTtsBackend(TtsBackend):
    def __init__(self):
        self.started_count = 0
        self.both_started = asyncio.Event()
        self.release = asyncio.Event()

    @property
    def backend_name(self) -> str:
        return "concurrent-tts"

    @property
    def sample_rate(self) -> int:
        return 22050

    @property
    def state(self) -> BackendReadyState:
        return BackendReadyState.READY

    async def synthesize(self, text, voice_id, speed, pitch, volume) -> TtsResult:
        self.started_count += 1
        if self.started_count == 2:
            self.both_started.set()
        await self.release.wait()
        return TtsResult(
            audio=np.zeros(22050, dtype=np.int16),
            sample_rate=22050,
            duration_ms=1000.0,
            processing_ms=2.0,
            rtf=0.002,
        )

    async def open_stream(self, voice_id, speed):
        raise NotImplementedError

    def get_voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(id="default", name="Concurrent", language="zh")]

    def get_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="concurrent",
                name="Concurrent TTS",
                capabilities=["tts"],
                languages=["zh"],
            )
        ]

    async def shutdown(self) -> None:
        return None


async def test_synthesize_does_not_hold_load_lock_during_backend_call():
    backend = _ConcurrentTtsBackend()
    service = TtsService(
        {"concurrent": backend},
        "concurrent",
        SessionStore(ttl_seconds=60, namespace="tts-concurrent-synth"),
    )

    first = asyncio.create_task(service.synthesize(SynthesizeRequest(text="你好")))
    second = asyncio.create_task(service.synthesize(SynthesizeRequest(text="世界")))
    await asyncio.wait_for(backend.both_started.wait(), timeout=1.0)

    backend.release.set()
    await first
    await second

    assert backend.started_count == 2


async def test_unload_waits_for_inflight_synthesis():
    backend = _BlockingTtsBackend()
    service = TtsService(
        {"blocking": backend},
        "blocking",
        SessionStore(ttl_seconds=60, namespace="tts-unload-waits"),
    )

    synth_task = asyncio.create_task(service.synthesize(SynthesizeRequest(text="你好")))
    await backend.started.wait()

    unload_task = asyncio.create_task(service.unload_model("blocking"))
    await asyncio.sleep(0)

    assert not unload_task.done()
    assert backend.shutdown_called is False

    backend.release.set()
    await synth_task
    await unload_task

    assert backend.shutdown_called is True
