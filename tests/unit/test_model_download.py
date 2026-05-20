from __future__ import annotations

import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from spacemit_ai_gateway.app.settings import AsrConfig, TtsConfig
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
    assert asr.warmup_audio_ms == 1000
    assert [model["id"] for model in asr.models] == ["sensevoice"]
    assert tts.backend == "matcha_zh_en"
    assert [model["id"] for model in tts.models] == ["matcha_zh_en"]


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


def test_tts_model_check_runs_before_sdk_import(monkeypatch, tmp_path):
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
    assert backend.state == BackendReadyState.DEGRADED


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
