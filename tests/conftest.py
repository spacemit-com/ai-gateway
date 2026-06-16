"""共用 fixtures。

说明：
- 真 adapter 在 spacemit_* SDK 缺失时自动降级到 mock，所以 integration / ws 测试
  可以直接起 app；不需要全局打桩。
- unit 测试为了隔离 service 层行为，提供 FakeAsrBackend / FakeTtsBackend / FakeVadBackend
  注入 service。
"""

from __future__ import annotations

import asyncio
import copy
from typing import AsyncGenerator, List

import httpx
import numpy as np
import pytest
import pytest_asyncio
import yaml

from spacemit_ai_gateway.common.ready_state import BackendReadyState
from spacemit_ai_gateway.common.schemas import ModelInfo, VoiceInfo
from spacemit_ai_gateway.common.sessions import SessionStore
from spacemit_ai_gateway.domains.asr.adapters.base import (
    AsrBackend,
    AsrEvent,
    AsrStreamSession,
    RecognitionResult,
)
from spacemit_ai_gateway.domains.asr.service import AsrService
from spacemit_ai_gateway.domains.tts.adapters.base import (
    TtsAudioChunk,
    TtsBackend,
    TtsDone,
    TtsResult,
    TtsStreamSession,
)
from spacemit_ai_gateway.domains.tts.service import TtsService
from spacemit_ai_gateway.domains.vad.adapters.base import (
    Segment,
    VadAnalysis,
    VadBackend,
    VadEvent,
    VadStreamSession,
)
from spacemit_ai_gateway.domains.vad.service import VadService


# ============================================================
# Fake backends
# ============================================================

class FakeAsrStream(AsrStreamSession):
    def __init__(self, loop):
        super().__init__(loop, queue_size=16)

    async def start(self) -> None:
        self._enqueue_threadsafe(AsrEvent(type="ready"))

    async def send_audio(self, chunk: bytes) -> None:
        self._enqueue_threadsafe(AsrEvent(type="partial", text="hi"))

    async def stop(self) -> RecognitionResult:
        result = RecognitionResult(text="fake final", duration_ms=10, processing_ms=1, rtf=0.1)
        self._enqueue_threadsafe(AsrEvent(type="final", text=result.text))
        self._enqueue_threadsafe(None)
        return result


class FakeAsrBackend(AsrBackend):
    @property
    def backend_name(self) -> str:
        return "fake-asr"

    @property
    def state(self) -> BackendReadyState:
        return BackendReadyState.READY

    async def recognize(
        self, audio, sample_rate, language, punctuation, hotwords=None,
        enable_emotion=False,
    ):
        return RecognitionResult(
            text="fake transcription",
            sentences=[{"text": "fake transcription", "start_ms": 0, "end_ms": 1000}],
            duration_ms=1000.0,
            processing_ms=2.0,
            rtf=0.002,
            language=language,
            emotion="happy" if enable_emotion else None,
        )

    async def create_stream(self, sample_rate, language, partial, enable_emotion=False):
        return FakeAsrStream(asyncio.get_running_loop())

    def get_supported_languages(self) -> List[str]:
        return ["zh", "en"]

    def get_models(self) -> List[ModelInfo]:
        return [
            ModelInfo(id="fake", name="Fake ASR", capabilities=["streaming", "emotion"], languages=["zh", "en"]),
        ]


class FakeTtsStream(TtsStreamSession):
    def __init__(self, loop):
        super().__init__(loop, queue_size=16)
        self._seq = 0

    async def start(self) -> None:
        return

    async def send_text(self, text: str) -> None:
        pcm = (np.zeros(100, dtype=np.int16)).tobytes()
        self._enqueue_threadsafe(TtsAudioChunk(pcm=pcm, seq=self._seq))
        self._seq += 1

    async def complete(self) -> None:
        self._enqueue_threadsafe(TtsDone(duration_ms=200, rtf=0.01))
        self._enqueue_threadsafe(None)


class FakeTtsBackend(TtsBackend):
    @property
    def backend_name(self) -> str:
        return "fake-tts"

    @property
    def sample_rate(self) -> int:
        return 22050

    @property
    def state(self) -> BackendReadyState:
        return BackendReadyState.READY

    async def synthesize(self, text, voice_id, speed, pitch, volume) -> TtsResult:
        return TtsResult(
            audio=np.zeros(22050, dtype=np.int16),
            sample_rate=22050,
            duration_ms=1000.0,
            processing_ms=2.0,
            rtf=0.002,
        )

    async def open_stream(self, voice_id, speed):
        return FakeTtsStream(asyncio.get_running_loop())

    def get_voices(self) -> List[VoiceInfo]:
        return [VoiceInfo(id="default", name="Fake", language="zh")]

    def get_models(self) -> List[ModelInfo]:
        return [ModelInfo(id="fake", name="Fake TTS", capabilities=["tts"], languages=["zh"])]


class FakeVadStream(VadStreamSession):
    def __init__(self, loop):
        super().__init__(loop, queue_size=16)

    async def start(self) -> None:
        return

    async def send_audio(self, chunk: bytes) -> None:
        self._enqueue_threadsafe(
            VadEvent(event="speech", probability=0.9, timestamp_ms=0.0)
        )

    async def stop(self) -> None:
        self._enqueue_threadsafe(None)


class FakeVadBackend(VadBackend):
    @property
    def backend_name(self) -> str:
        return "fake-vad"

    @property
    def state(self) -> BackendReadyState:
        return BackendReadyState.READY

    async def analyze(self, audio, sample_rate) -> VadAnalysis:
        return VadAnalysis(is_speech=True, probability=0.9, smoothed_probability=0.9, processing_ms=1.0)

    async def segment(self, audio, sample_rate):
        duration_ms = 1000.0
        return [Segment(start_ms=0, end_ms=duration_ms, confidence=0.9)], duration_ms

    async def open_stream(self, sample_rate):
        return FakeVadStream(asyncio.get_running_loop())

    def get_params(self) -> dict:
        return {
            "trigger_threshold": 0.5,
            "stop_threshold": 0.35,
            "min_speech_ms": 250,
            "max_silence_ms": 500,
            "sample_rate": 16000,
        }


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def fake_asr_backend() -> FakeAsrBackend:
    return FakeAsrBackend()


@pytest.fixture
def fake_tts_backend() -> FakeTtsBackend:
    return FakeTtsBackend()


@pytest.fixture
def fake_vad_backend() -> FakeVadBackend:
    return FakeVadBackend()


@pytest.fixture
def asr_service(fake_asr_backend) -> AsrService:
    return AsrService(
        {"fake": fake_asr_backend},
        "fake",
        SessionStore(ttl_seconds=60, namespace="asr"),
    )


@pytest.fixture
def tts_service(fake_tts_backend) -> TtsService:
    return TtsService(
        {"fake": fake_tts_backend},
        "fake",
        SessionStore(ttl_seconds=60, namespace="tts"),
    )


@pytest.fixture
def vad_service(fake_vad_backend) -> VadService:
    return VadService({"fake": fake_vad_backend}, "fake")


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch) -> AsyncGenerator[httpx.AsyncClient, None]:
    """直连 app。ASGITransport 不会自动跑 lifespan，所以这里显式进入
    `app.router.lifespan_context` 来 trigger startup / shutdown，让
    `app.state.*_service` 被装配。"""
    from spacemit_ai_gateway.app.settings import get_settings, load_yaml_config

    config = copy.deepcopy(load_yaml_config())
    for domain in ("llm", "embed", "rerank"):
        storage = config[domain]["storage"]
        storage["db_path"] = str(tmp_path / domain / "db.sqlite")

    config_path = tmp_path / "base.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("SPACEMIT_AI_GATEWAY_CONFIG", str(config_path))
    get_settings.cache_clear()

    from spacemit_ai_gateway.app.main import app as real_app

    try:
        async with real_app.router.lifespan_context(real_app):
            transport = httpx.ASGITransport(app=real_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                yield c
    finally:
        get_settings.cache_clear()
