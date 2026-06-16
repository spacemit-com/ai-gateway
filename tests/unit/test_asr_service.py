"""ASR service 单元测试。"""

from __future__ import annotations

import pytest

from spacemit_ai_gateway.app.settings import AsrConfig
from spacemit_ai_gateway.common.errors import InvalidSessionError, ModelUnknown
from spacemit_ai_gateway.common.ready_state import BackendReadyState
from spacemit_ai_gateway.common.schemas import ModelInfo
from spacemit_ai_gateway.common.sessions import SessionStore
from spacemit_ai_gateway.domains.asr.adapters.base import AsrBackend, RecognitionResult
from spacemit_ai_gateway.domains.asr import service as service_module
from spacemit_ai_gateway.domains.asr.schemas import (
    AsrParamsPatch,
    RecognizeParams,
    StreamSessionRequest,
)
from spacemit_ai_gateway.domains.asr.service import AsrService


class NoEmotionAsrBackend(AsrBackend):
    @property
    def backend_name(self) -> str:
        return "no-emotion-asr"

    @property
    def state(self) -> BackendReadyState:
        return BackendReadyState.READY

    async def recognize(
        self, audio, sample_rate, language, punctuation, hotwords=None,
        enable_emotion=False,
    ):
        return RecognitionResult(
            text="fake transcription",
            duration_ms=1000.0,
            processing_ms=2.0,
            rtf=0.002,
            language=language,
            emotion="should-not-leak" if enable_emotion else None,
        )

    async def create_stream(self, sample_rate, language, partial, enable_emotion=False):
        raise NotImplementedError

    def get_supported_languages(self):
        return ["zh", "en"]

    def get_models(self):
        return [
            ModelInfo(
                id="qwen3-asr",
                name="Qwen3-ASR",
                capabilities=["multilingual"],
                languages=["zh", "en"],
            ),
        ]


class ReloadableSenseVoiceBackend(AsrBackend):
    model_id = "sensevoice"
    model_name = "SenseVoice"
    metadata_available = True
    shutdown_count = 0

    def __init__(self, config: AsrConfig):
        self._config = config
        self._state = BackendReadyState.READY
        self._emotion_enabled = self.metadata_available

    @property
    def backend_name(self) -> str:
        return self.model_id

    @property
    def state(self) -> BackendReadyState:
        return self._state

    @property
    def emotion_enabled(self) -> bool:
        return self._emotion_enabled

    async def recognize(
        self, audio, sample_rate, language, punctuation, hotwords=None,
        enable_emotion=False,
    ):
        return RecognitionResult(
            text="sensevoice transcription",
            duration_ms=1000.0,
            processing_ms=2.0,
            rtf=0.002,
            language=language,
            emotion="happy" if enable_emotion else None,
        )

    async def create_stream(self, sample_rate, language, partial, enable_emotion=False):
        raise NotImplementedError

    def get_supported_languages(self):
        return ["zh", "en", "auto"]

    def get_models(self):
        return [
            ModelInfo(
                id=self.model_id,
                name=self.model_name,
                capabilities=["multilingual", "streaming", "emotion"],
                languages=["zh", "en", "auto"],
            ),
        ]

    def get_params(self):
        return {
            "language": self._config.language,
            "punctuation": self._config.punctuation,
            "hotword_weight": None,
            "itn": None,
            "enable_emotion": self._config.enable_emotion,
        }

    async def shutdown(self) -> None:
        type(self).shutdown_count += 1


class ReloadableFutureEmotionBackend(ReloadableSenseVoiceBackend):
    model_id = "future-emotion-asr"
    model_name = "Future Emotion ASR"


async def test_recognize_returns_text(asr_service):
    resp = await asr_service.recognize(
        b"\x00" * 16000,
        RecognizeParams(language="zh", sample_rate=16000),
    )
    assert resp.text == "fake transcription"
    assert resp.duration_ms > 0
    assert len(resp.sentences) == 1
    assert resp.emotion is None


async def test_recognize_can_enable_emotion(asr_service):
    resp = await asr_service.recognize(
        b"\x00" * 16000,
        RecognizeParams(language="zh", sample_rate=16000, enable_emotion=True),
    )
    assert resp.text == "fake transcription"
    assert resp.emotion == "happy"


async def test_recognize_ignores_emotion_for_unsupported_model():
    service = AsrService(
        {"qwen3-asr": NoEmotionAsrBackend()},
        "qwen3-asr",
        SessionStore(ttl_seconds=60, namespace="asr-no-emotion"),
        config=AsrConfig(backend="qwen3-asr", backends=["qwen3-asr"]),
    )
    resp = await service.recognize(
        b"\x00" * 16000,
        RecognizeParams(
            model="qwen3-asr",
            language="zh",
            sample_rate=16000,
            enable_emotion=True,
        ),
    )
    assert resp.emotion is None


async def test_explicit_false_overrides_default_emotion(monkeypatch):
    monkeypatch.setitem(
        service_module.ASR_REGISTRY, "sensevoice", ReloadableSenseVoiceBackend
    )
    config = AsrConfig(
        backend="sensevoice",
        backends=["sensevoice"],
        enable_emotion=True,
    )
    existing = ReloadableSenseVoiceBackend(config)
    service = AsrService(
        {"sensevoice": existing},
        "sensevoice",
        SessionStore(ttl_seconds=60, namespace="asr-explicit-false"),
        config=config,
    )
    ReloadableSenseVoiceBackend.shutdown_count = 0

    resp = await service.recognize(
        b"\x00" * 16000,
        RecognizeParams(
            model="sensevoice",
            language="zh",
            sample_rate=16000,
            enable_emotion=False,
        ),
    )

    assert resp.emotion is None
    assert service._backends["sensevoice"] is existing
    assert service._backends["sensevoice"].emotion_enabled is True
    assert service._backends["sensevoice"]._config.enable_emotion is True
    assert ReloadableSenseVoiceBackend.shutdown_count == 0


async def test_request_emotion_true_does_not_reload_backend(monkeypatch):
    monkeypatch.setitem(
        service_module.ASR_REGISTRY, "sensevoice", ReloadableSenseVoiceBackend
    )
    ReloadableSenseVoiceBackend.shutdown_count = 0
    config = AsrConfig(
        backend="sensevoice",
        backends=["sensevoice"],
        enable_emotion=False,
    )
    existing = ReloadableSenseVoiceBackend(config)
    service = AsrService(
        {"sensevoice": existing},
        "sensevoice",
        SessionStore(ttl_seconds=60, namespace="asr-request-emotion"),
        config=config,
    )

    resp = await service.recognize(
        b"\x00" * 16000,
        RecognizeParams(
            model="sensevoice",
            language="zh",
            sample_rate=16000,
            enable_emotion=True,
        ),
    )

    assert resp.emotion == "happy"
    assert service._backends["sensevoice"] is existing
    assert ReloadableSenseVoiceBackend.shutdown_count == 0


async def test_update_params_reloads_loaded_backend_for_emotion(monkeypatch):
    monkeypatch.setitem(
        service_module.ASR_REGISTRY, "sensevoice", ReloadableSenseVoiceBackend
    )
    ReloadableSenseVoiceBackend.shutdown_count = 0
    config = AsrConfig(
        backend="sensevoice",
        backends=["sensevoice"],
        enable_emotion=False,
    )
    existing = ReloadableSenseVoiceBackend(config)
    existing._emotion_enabled = False
    service = AsrService(
        {"sensevoice": existing},
        "sensevoice",
        SessionStore(ttl_seconds=60, namespace="asr-param-emotion"),
        config=config,
    )

    params = await service.update_params(AsrParamsPatch(enable_emotion=True))

    assert params.enable_emotion is True
    assert service._config.enable_emotion is True
    assert service._backends["sensevoice"] is not existing
    assert service._backends["sensevoice"].emotion_enabled is True
    assert service._engine_pending_restart is False
    assert ReloadableSenseVoiceBackend.shutdown_count == 1


async def test_update_params_emotion_keeps_engine_pending_without_reload(monkeypatch):
    monkeypatch.setitem(
        service_module.ASR_REGISTRY, "sensevoice", ReloadableSenseVoiceBackend
    )
    ReloadableSenseVoiceBackend.shutdown_count = 0
    config = AsrConfig(
        backend="sensevoice",
        backends=["sensevoice"],
        enable_emotion=False,
    )
    existing = ReloadableSenseVoiceBackend(config)
    service = AsrService(
        {"sensevoice": existing},
        "sensevoice",
        SessionStore(ttl_seconds=60, namespace="asr-param-pending"),
        config=config,
    )
    service._engine_pending_restart = True

    params = await service.update_params(AsrParamsPatch(enable_emotion=True))

    assert params.enable_emotion is True
    assert service._config.enable_emotion is True
    assert service._backends["sensevoice"] is existing
    assert service._engine_pending_restart is True
    assert ReloadableSenseVoiceBackend.shutdown_count == 0


async def test_update_params_emotion_reload_is_capability_based(monkeypatch):
    monkeypatch.setitem(
        service_module.ASR_REGISTRY,
        "future-emotion-asr",
        ReloadableFutureEmotionBackend,
    )
    ReloadableFutureEmotionBackend.shutdown_count = 0
    config = AsrConfig(
        backend="future-emotion-asr",
        backends=["future-emotion-asr"],
        enable_emotion=False,
    )
    existing = ReloadableFutureEmotionBackend(config)
    existing._emotion_enabled = False
    service = AsrService(
        {"future-emotion-asr": existing},
        "future-emotion-asr",
        SessionStore(ttl_seconds=60, namespace="asr-future-emotion"),
        config=config,
    )

    params = await service.update_params(AsrParamsPatch(enable_emotion=True))

    assert params.enable_emotion is True
    assert service._backends["future-emotion-asr"] is not existing
    assert service._backends["future-emotion-asr"].emotion_enabled is True
    assert ReloadableFutureEmotionBackend.shutdown_count == 1


async def test_create_stream_session_and_open(asr_service):
    ss = await asr_service.create_stream_session(
        StreamSessionRequest(sample_rate=16000, language="zh")
    )
    assert ss.session_id
    # open 时 pop 后就不复存在
    stream = await asr_service.open_stream(
        session_id=ss.session_id, language="zh", sample_rate=16000, partial=True
    )
    assert stream is not None


async def test_open_stream_without_session_raises(asr_service):
    with pytest.raises(InvalidSessionError):
        await asr_service.open_stream(
            session_id=None, language="zh", sample_rate=16000, partial=True
        )


async def test_open_stream_with_bad_session_raises(asr_service):
    with pytest.raises(InvalidSessionError):
        await asr_service.open_stream(
            session_id="nonexistent", language="zh", sample_rate=16000, partial=True
        )


async def test_healthz_ready(asr_service):
    h = await asr_service.healthz()
    assert h["ready"] is True
    assert h["backend"] == "fake-asr"


def test_get_models_respects_configured_backends():
    service = AsrService(
        {},
        "sensevoice",
        SessionStore(ttl_seconds=60, namespace="asr-allow-list"),
        config=AsrConfig(backend="sensevoice", backends=["sensevoice"]),
    )

    assert [model.id for model in service.get_models()] == ["sensevoice"]


async def test_load_rejects_unconfigured_backend():
    service = AsrService(
        {},
        "sensevoice",
        SessionStore(ttl_seconds=60, namespace="asr-allow-list"),
        config=AsrConfig(backend="sensevoice", backends=["sensevoice"]),
    )

    with pytest.raises(ModelUnknown) as exc_info:
        await service.load_model("qwen3-asr")

    assert exc_info.value.details == {"available": ["sensevoice"]}
