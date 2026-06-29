from __future__ import annotations

import asyncio
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from spacemit_ai_gateway.app.settings import AsrConfig, TtsConfig
from spacemit_ai_gateway.common.errors import TtsBackendUnavailable
from spacemit_ai_gateway.common.model_download import (
    ensure_archive_model,
    ensure_remote_file,
)
from spacemit_ai_gateway.common.ready_state import BackendReadyState


def test_ensure_archive_model_flattens_archive_subdir(tmp_path):
    source_dir = tmp_path / "source" / "sensevoice"
    source_dir.mkdir(parents=True)
    (source_dir / "tokens.txt").write_text("tokens", encoding="utf-8")

    archive_path = tmp_path / "sensevoice.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(source_dir, arcname="sensevoice")

    model_dir = tmp_path / "models" / "sensevoice"
    ensure_archive_model(
        model_dir,
        url=archive_path.as_uri(),
        archive_name="sensevoice.tar.gz",
        archive_subdir="sensevoice",
        required_paths=("tokens.txt",),
    )

    assert (model_dir / "tokens.txt").read_text(encoding="utf-8") == "tokens"


def test_ensure_remote_file_downloads_file_url(tmp_path):
    source = tmp_path / "source.onnx"
    source.write_bytes(b"model")

    target = tmp_path / "models" / "target.onnx"
    ensure_remote_file(target, source.as_uri())

    assert target.read_bytes() == b"model"


def test_speech_defaults_use_single_startup_models():
    asr = AsrConfig()
    tts = TtsConfig()

    assert asr.backend == "sensevoice"
    assert asr.language == "auto"
    assert asr.warmup_audio_ms == 1000
    assert [model["id"] for model in asr.models] == ["sensevoice"]
    assert tts.backend == "matcha_zh_en"
    assert [model["id"] for model in tts.models] == ["matcha_zh_en"]
    assert tts.models[0]["vocoder_name"] == "vocos-16khz-univ.q.onnx"
    assert tts.models[0]["vocoder_url"].endswith("/vocos-16khz-univ.q.onnx")


def test_asr_model_check_runs_before_sdk_import(monkeypatch, tmp_path):
    from spacemit_ai_gateway.domains.asr.adapters import sensevoice

    calls = []

    def fake_ensure(model_dir, **kwargs):
        calls.append((model_dir, kwargs))

    monkeypatch.setattr(sensevoice, "_DEFAULT_MODEL_DIR", str(tmp_path / "asr" / "sensevoice"))
    monkeypatch.setattr(sensevoice, "ensure_archive_model", fake_ensure)
    monkeypatch.setitem(sys.modules, "spacemit_asr", None)

    backend = sensevoice.SenseVoiceBackend(AsrConfig())

    assert calls
    assert calls[0][0] == tmp_path / "asr" / "sensevoice"
    assert backend.state == BackendReadyState.DEGRADED


@pytest.mark.asyncio
async def test_sensevoice_warmup_runs_fixed_length_audio(monkeypatch, tmp_path):
    from spacemit_ai_gateway.domains.asr.adapters import sensevoice

    engine_instances = []

    class FakeLanguage:
        AUTO = "auto"
        ZH = "zh"
        EN = "en"
        JA = "ja"
        KO = "ko"
        YUE = "yue"

    class FakeConfig:
        def __init__(self, model_dir):
            self.model_dir = model_dir
            self.language = None
            self.punctuation_enabled = None
            self.provider = None

    class FakeResult:
        text = ""
        audio_duration_ms = 250.0
        processing_time_ms = 1.0
        rtf = 0.004

    class FakeEngine:
        def __init__(self, config):
            self.config = config
            self.recognize_calls = []
            engine_instances.append(self)

        def initialize(self):
            return None

        def recognize(self, samples):
            self.recognize_calls.append(samples.copy())
            return FakeResult()

    fake_spacemit_asr = SimpleNamespace(
        Language=FakeLanguage,
        Config=FakeConfig,
        Engine=FakeEngine,
    )

    monkeypatch.setattr(sensevoice, "ensure_archive_model", lambda *a, **kw: None)
    monkeypatch.setitem(sys.modules, "spacemit_asr", fake_spacemit_asr)

    backend = sensevoice.SenseVoiceBackend(
        AsrConfig(model_dir=str(tmp_path / "asr"), warmup_audio_ms=250)
    )

    await backend.warmup()

    assert backend.state == BackendReadyState.READY
    assert len(engine_instances) == 1
    assert len(engine_instances[0].recognize_calls) == 1
    samples = engine_instances[0].recognize_calls[0]
    assert samples.dtype.name == "int16"
    assert samples.shape == (4000,)
    assert samples.sum() == 0
    assert engine_instances[0].config.language == "auto"


def test_sensevoice_resamples_pcm_to_model_rate():
    from spacemit_ai_gateway.domains.asr.adapters import sensevoice

    samples = np.arange(22050, dtype=np.int16)

    prepared = sensevoice._pcm16_bytes_to_model_samples(
        samples.tobytes() + b"x",
        sample_rate=22050,
    )

    assert prepared.dtype.name == "int16"
    assert prepared.shape == (16000,)
    assert prepared[0] == samples[0]
    assert prepared[-1] == samples[-1]


def test_tts_model_check_runs_before_worker_start(monkeypatch, tmp_path):
    from spacemit_ai_gateway.domains.tts.adapters import matcha

    calls = []

    def fake_ensure(backend, model_dir, configured_models):
        calls.append((backend, model_dir, configured_models))

    monkeypatch.setattr(matcha, "_DEFAULT_MODEL_DIR", str(tmp_path / "tts" / "matcha-tts"))
    monkeypatch.setattr(matcha, "_ensure_model_assets", fake_ensure)
    monkeypatch.setitem(sys.modules, "spacemit_tts", None)

    backend = matcha.MatchaBackend(TtsConfig())

    assert calls
    assert calls[0][0] == "matcha_zh_en"
    assert calls[0][1] == tmp_path / "tts" / "matcha-tts"
    assert backend.state == BackendReadyState.WARMING_UP
    assert backend._worker is not None


def test_tts_startup_loads_only_default_backend(monkeypatch):
    from spacemit_ai_gateway.domains.tts import adapters

    calls = []

    class FakeBackend:
        def __init__(self, config):
            calls.append(config.backend)

    monkeypatch.setitem(adapters._REGISTRY, "matcha_zh_en", FakeBackend)
    monkeypatch.setitem(adapters._REGISTRY, "matcha_zh", FakeBackend)
    monkeypatch.setitem(adapters._REGISTRY, "matcha_en", FakeBackend)

    backends = adapters.build_tts_backends(
        TtsConfig(
            backend="matcha_zh_en",
            backends=["matcha_zh_en", "matcha_zh", "matcha_en"],
        )
    )

    assert list(backends) == ["matcha_zh_en"]
    assert calls == ["matcha_zh_en"]


@pytest.mark.asyncio
async def test_matcha_warmup_runs_worker_synthesis(monkeypatch, tmp_path):
    from spacemit_ai_gateway.domains.tts.adapters import matcha

    worker_instances = []

    class FakeWorker:
        def __init__(self, config):
            self.config = config
            self.warmup_calls = []
            worker_instances.append(self)

        async def start(self):
            return {"sample_rate": 16000}

        async def warmup(self, text):
            self.warmup_calls.append(text)

    monkeypatch.setattr(matcha, "_ensure_model_assets", lambda *a, **kw: None)
    monkeypatch.setattr(matcha, "NativeTtsWorker", FakeWorker)

    backend = matcha.MatchaBackend(
        TtsConfig(backend="matcha_zh_en", model_dir=str(tmp_path / "tts"))
    )

    await backend.warmup()

    assert backend.state == BackendReadyState.READY
    assert len(worker_instances) == 1
    assert worker_instances[0].warmup_calls == ["你好"]
    assert worker_instances[0].config.model_dir == str(tmp_path / "tts")
    assert backend.sample_rate == 16000


@pytest.mark.asyncio
async def test_matcha_worker_start_failure_falls_back_to_mock(monkeypatch, tmp_path):
    from spacemit_ai_gateway.domains.tts.adapters import matcha

    worker_instances = []

    class FakeWorker:
        def __init__(self, config):
            self.stop_calls = []
            worker_instances.append(self)

        async def start(self):
            raise RuntimeError("missing spacemit_tts")

        async def warmup(self, text):
            raise AssertionError("warmup should not run after start failure")

        async def stop(self, *, kill=False):
            self.stop_calls.append(kill)

    monkeypatch.setattr(matcha, "_ensure_model_assets", lambda *a, **kw: None)
    monkeypatch.setattr(matcha, "NativeTtsWorker", FakeWorker)

    backend = matcha.MatchaBackend(
        TtsConfig(backend="matcha_zh_en", model_dir=str(tmp_path / "tts"))
    )

    await backend.warmup()

    assert backend.state == BackendReadyState.DEGRADED
    assert backend._mock is True
    assert backend._worker is None
    assert worker_instances[0].stop_calls == [True]
    result = await backend.synthesize("你好", None, 1.0, 1.0, 1.0)
    assert result.sample_rate == backend.sample_rate


@pytest.mark.asyncio
async def test_matcha_worker_warmup_cancellation_stops_worker(monkeypatch, tmp_path):
    from spacemit_ai_gateway.domains.tts.adapters import matcha

    worker_instances = []

    class FakeWorker:
        def __init__(self, config):
            self.stop_calls = []
            worker_instances.append(self)

        async def start(self):
            return {"sample_rate": 16000}

        async def warmup(self, text):
            raise asyncio.CancelledError()

        async def stop(self, *, kill=False):
            self.stop_calls.append(kill)

    monkeypatch.setattr(matcha, "_ensure_model_assets", lambda *a, **kw: None)
    monkeypatch.setattr(matcha, "NativeTtsWorker", FakeWorker)

    backend = matcha.MatchaBackend(
        TtsConfig(backend="matcha_zh_en", model_dir=str(tmp_path / "tts"))
    )

    with pytest.raises(asyncio.CancelledError):
        await backend.warmup()

    assert backend.state == BackendReadyState.DEGRADED
    assert backend._mock is True
    assert backend._worker is None
    assert worker_instances[0].stop_calls == [True]


@pytest.mark.asyncio
async def test_matcha_worker_warmup_failure_stops_worker(monkeypatch, tmp_path):
    from spacemit_ai_gateway.domains.tts.adapters import matcha

    worker_instances = []

    class FakeWorker:
        def __init__(self, config):
            self.stop_calls = []
            worker_instances.append(self)

        async def start(self):
            return {"sample_rate": 16000}

        async def warmup(self, text):
            raise RuntimeError("warmup failed")

        async def stop(self, *, kill=False):
            self.stop_calls.append(kill)

    monkeypatch.setattr(matcha, "_ensure_model_assets", lambda *a, **kw: None)
    monkeypatch.setattr(matcha, "NativeTtsWorker", FakeWorker)

    backend = matcha.MatchaBackend(
        TtsConfig(backend="matcha_zh_en", model_dir=str(tmp_path / "tts"))
    )

    await backend.warmup()

    assert backend.state == BackendReadyState.DEGRADED
    assert backend._mock is True
    assert backend._worker is None
    assert backend.sample_rate == 16000
    assert worker_instances[0].stop_calls == [True]


@pytest.mark.asyncio
async def test_matcha_shutdown_stops_worker(monkeypatch, tmp_path):
    from spacemit_ai_gateway.domains.tts.adapters import matcha

    worker_instances = []

    class FakeWorker:
        def __init__(self, config):
            self.stopped = False
            worker_instances.append(self)

        async def start(self):
            return {"sample_rate": 16000}

        async def warmup(self, text):
            return None

        async def stop(self):
            self.stopped = True

    monkeypatch.setattr(matcha, "_ensure_model_assets", lambda *a, **kw: None)
    monkeypatch.setattr(matcha, "NativeTtsWorker", FakeWorker)

    backend = matcha.MatchaBackend(
        TtsConfig(backend="matcha_zh_en", model_dir=str(tmp_path / "tts"))
    )

    await backend.warmup()
    await backend.shutdown()

    assert backend.state == BackendReadyState.IDLE
    assert backend._worker is None
    assert worker_instances[0].stopped is True
    with pytest.raises(TtsBackendUnavailable):
        await backend.synthesize("你好", None, 1.0, 1.0, 1.0)


@pytest.mark.asyncio
async def test_native_worker_stream_protocol_forwards_chunks(monkeypatch, tmp_path):
    import asyncio
    import os

    from spacemit_ai_gateway.domains.tts.adapters.native_worker import NativeTtsWorker

    fake_module = r"""
import numpy as np

class Config:
    @classmethod
    def preset(cls, backend):
        cfg = cls()
        cfg.backend = backend
        cfg.model_dir = ""
        cfg.sample_rate = 16000
        cfg.speed = 1.0
        return cfg

class TtsCallback:
    pass

class _RawResult:
    is_success = True
    message = ""

    def __init__(self, audio, duration_ms, processing_time_ms, rtf):
        self.audio_int16 = np.asarray(audio, dtype=np.int16)
        self.sample_rate = 16000
        self.duration_ms = duration_ms
        self.processing_time_ms = processing_time_ms
        self.rtf = rtf

class _StreamResult:
    def __init__(self, audio, duration_ms, rtf):
        self._audio = np.asarray(audio, dtype=np.int16)
        self._duration_ms = duration_ms
        self._rtf = rtf

    def get_audio_int16(self):
        return self._audio

    def get_duration_ms(self):
        return self._duration_ms

    def get_rtf(self):
        return self._rtf

class Engine:
    def __init__(self, config):
        self.config = config

    def synthesize(self, text):
        return _RawResult([0], 1.0, 1.0, 1.0)

    def synthesize_streaming(self, text, callback):
        callback.on_event(_StreamResult([1, 2], 10.0, 0.1))
        callback.on_event(_StreamResult([3, 4, 5], 20.0, 0.2))

    def shutdown(self):
        pass
"""
    (tmp_path / "spacemit_tts.py").write_text(fake_module, encoding="utf-8")
    repo_src = Path(__file__).resolve().parents[2] / "src"
    old_pythonpath = os.environ.get("PYTHONPATH")
    pythonpath = f"{tmp_path}:{repo_src}"
    if old_pythonpath:
        pythonpath = f"{pythonpath}:{old_pythonpath}"
    monkeypatch.setenv("PYTHONPATH", pythonpath)

    worker = NativeTtsWorker(
        TtsConfig(backend="matcha_zh_en", model_dir=str(tmp_path / "tts")),
        startup_timeout_s=5.0,
        request_timeout_s=5.0,
    )

    async def collect_events():
        events = []
        async for event in worker.stream_synthesize("你好"):
            events.append(event)
        return events

    try:
        events = await asyncio.wait_for(collect_events(), timeout=5.0)
    finally:
        await worker.stop(kill=True)

    assert [event["type"] for event in events] == ["audio", "audio", "done"]
    assert events[0]["audio"].tolist() == [1, 2]
    assert events[1]["audio"].tolist() == [3, 4, 5]
    assert events[2]["duration_ms"] == 30.0
    assert events[2]["rtf"] == 0.2


@pytest.mark.asyncio
async def test_matcha_stream_forwards_worker_audio_events(monkeypatch, tmp_path):
    from spacemit_ai_gateway.domains.tts.adapters import matcha

    class FakeWorker:
        def __init__(self, config):
            self.stream_calls = []

        async def start(self):
            return {"sample_rate": 16000}

        async def warmup(self, text):
            return None

        async def stream_synthesize(self, text):
            self.stream_calls.append(text)
            yield {
                "type": "audio",
                "audio": np.array([1, 2], dtype=np.int16),
                "duration_ms": 10.0,
                "rtf": 0.1,
            }
            yield {
                "type": "audio",
                "audio": np.array([3, 4, 5], dtype=np.int16),
                "duration_ms": 20.0,
                "rtf": 0.2,
            }
            yield {"type": "done", "duration_ms": 30.0, "rtf": 0.2}

        async def stop(self):
            return None

    monkeypatch.setattr(matcha, "_ensure_model_assets", lambda *a, **kw: None)
    monkeypatch.setattr(matcha, "NativeTtsWorker", FakeWorker)

    backend = matcha.MatchaBackend(
        TtsConfig(backend="matcha_zh_en", model_dir=str(tmp_path / "tts"))
    )
    await backend.warmup()

    stream = await backend.open_stream(voice_id=None, speed=1.0)
    await stream.send_text("你好")
    await stream.complete()

    first = await stream.recv()
    second = await stream.recv()
    done = await stream.recv()

    assert first.pcm == np.array([1, 2], dtype=np.int16).tobytes()
    assert second.pcm == np.array([3, 4, 5], dtype=np.int16).tobytes()
    assert done.duration_ms == 30.0
    assert done.rtf == 0.2
    assert await stream.recv() is None


@pytest.mark.asyncio
async def test_kokoro_shutdown_releases_engine(monkeypatch):
    from spacemit_ai_gateway.domains.tts.adapters import kokoro

    class FakeConfig:
        def __init__(self):
            self.sample_rate = 24000
            self.speed = 1.0

        @classmethod
        def preset(cls, backend):
            return cls()

    class FakeResult:
        is_success = True
        message = "ok"
        audio_int16 = np.zeros(10, dtype=np.int16)
        sample_rate = 24000
        duration_ms = 1.0
        processing_time_ms = 1.0
        rtf = 1.0

    class FakeEngine:
        def __init__(self, config):
            self.config = config

        def synthesize(self, text):
            return FakeResult()

    fake_spacemit_tts = SimpleNamespace(Config=FakeConfig, Engine=FakeEngine)

    monkeypatch.setitem(sys.modules, "spacemit_tts", fake_spacemit_tts)

    backend = kokoro.KokoroBackend(TtsConfig(backend="kokoro"))

    await backend.warmup()
    await backend.shutdown()

    assert backend.state == BackendReadyState.IDLE
    assert backend._engine is None
    with pytest.raises(TtsBackendUnavailable):
        await backend.synthesize("你好", None, 1.0, 1.0, 1.0)


def test_matcha_assets_expect_quantized_models():
    from spacemit_ai_gateway.domains.tts.adapters import matcha

    for asset in matcha._MODEL_ASSETS.values():
        required_paths = asset["required_paths"]
        assert asset["vocoder_name"].endswith(".q.onnx")
        assert asset["vocoder_url"].endswith(".q.onnx")
        assert any(path.endswith("model-steps-3.q.onnx") for path in required_paths)
        assert not any(
            path.endswith(".onnx") and not path.endswith(".q.onnx")
            for path in required_paths
        )


def test_vision_label_path_materializes_package_resource(monkeypatch, tmp_path):
    from spacemit_ai_gateway.domains.vision import models

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    source_config = tmp_path / "yolov8.yaml"
    source_config.write_text(
        "label_file_path: spacemit_ai_gateway/domains/vision/assets/labels/coco.txt\n",
        encoding="utf-8",
    )

    runtime_config = Path(models._materialize_config_for_runtime(str(source_config)))

    assert runtime_config != source_config
    assert runtime_config.exists()
    assert str(tmp_path / "cache") in str(runtime_config)
    assert str(models._package_root()) in runtime_config.read_text(encoding="utf-8")
