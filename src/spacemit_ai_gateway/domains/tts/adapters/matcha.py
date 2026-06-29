"""Matcha TTS backend（支持 matcha_zh/matcha_en/matcha_zh_en）。

模型缺失时先下载到 model_dir，再初始化 spacemit_tts Engine。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import List, Optional

import numpy as np

from ....app.settings import TtsConfig
from ....common.errors import TtsBackendUnavailable, TtsInvalidText
from ....common.model_download import ensure_archive_model, ensure_remote_file, expand_path
from ....common.ready_state import BackendReadyState
from ....common.schemas import ModelInfo, VoiceInfo
from .base import (
    TtsAudioChunk,
    TtsBackend,
    TtsDone,
    TtsResult,
    TtsStreamSession,
)
from .native_worker import NativeTtsWorker

logger = logging.getLogger(__name__)
logger_bridge = logging.getLogger(f"{__name__}._Bridge")

_DEFAULT_SAMPLE_RATES = {
    "matcha_zh": 22050,
    "matcha_en": 22050,
    "matcha_zh_en": 16000,
}

_DEFAULT_MODEL_DIR = "~/.cache/models/tts/matcha-tts"
_VOCODER_22K_URL = "https://archive.spacemit.com/spacemit-ai/model_zoo/tts/vocoder/vocos-22khz-univ.q.onnx"
_VOCODER_16K_URL = "https://archive.spacemit.com/spacemit-ai/model_zoo/tts/vocoder/vocos-16khz-univ.q.onnx"
_WARMUP_TEXT = {
    "matcha_zh": "你好",
    "matcha_en": "hello",
    "matcha_zh_en": "你好",
}
_MODEL_ASSETS = {
    "matcha_zh": {
        "url": "https://archive.spacemit.com/spacemit-ai/model_zoo/tts/matcha-tts/matcha-icefall-zh-baker.tar.gz",
        "archive_name": "matcha-icefall-zh-baker.tar.gz",
        "required_paths": (
            "matcha-icefall-zh-baker/model-steps-3.q.onnx",
            "matcha-icefall-zh-baker/lexicon.txt",
            "matcha-icefall-zh-baker/tokens.txt",
            "matcha-icefall-zh-baker/dict",
            "vocos-22khz-univ.q.onnx",
        ),
        "vocoder_name": "vocos-22khz-univ.q.onnx",
        "vocoder_url": _VOCODER_22K_URL,
    },
    "matcha_en": {
        "url": "https://archive.spacemit.com/spacemit-ai/model_zoo/tts/matcha-tts/matcha-icefall-en_US-ljspeech.tar.gz",
        "archive_name": "matcha-icefall-en_US-ljspeech.tar.gz",
        "required_paths": (
            "matcha-icefall-en_US-ljspeech/model-steps-3.q.onnx",
            "matcha-icefall-en_US-ljspeech/tokens.txt",
            "matcha-icefall-en_US-ljspeech/espeak-ng-data",
            "vocos-22khz-univ.q.onnx",
        ),
        "vocoder_name": "vocos-22khz-univ.q.onnx",
        "vocoder_url": _VOCODER_22K_URL,
    },
    "matcha_zh_en": {
        "url": "https://archive.spacemit.com/spacemit-ai/model_zoo/tts/matcha-tts/matcha-icefall-zh-en.tar.gz",
        "archive_name": "matcha-icefall-zh-en.tar.gz",
        "required_paths": (
            "matcha-icefall-zh-en/model-steps-3.q.onnx",
            "matcha-icefall-zh-en/vocab_tts.txt",
            "vocos-16khz-univ.q.onnx",
        ),
        "vocoder_name": "vocos-16khz-univ.q.onnx",
        "vocoder_url": _VOCODER_16K_URL,
    },
}


_VOICES = {
    "matcha_zh": [
        VoiceInfo(id="default", name="默认中文", language="zh", gender="female"),
    ],
    "matcha_en": [
        VoiceInfo(id="default", name="Default English", language="en", gender="female"),
    ],
    "matcha_zh_en": [
        VoiceInfo(id="default", name="中英混合", language="zh-en", gender="female"),
    ],
}


class MatchaBackend(TtsBackend):
    def __init__(self, config: TtsConfig):
        self._config = config
        self._mock = False
        self._worker: NativeTtsWorker | None = None
        self._engine_lock = asyncio.Lock()
        self._closed = False
        self._engine_sample_rate = (
            config.sample_rate
            or _DEFAULT_SAMPLE_RATES.get(config.backend, 22050)
        )
        self._state = BackendReadyState.INITIALIZING

        model_dir = expand_path(config.model_dir or _DEFAULT_MODEL_DIR)
        try:
            _ensure_model_assets(config.backend, model_dir, config.models)
        except Exception as e:
            logger.exception("TTS model check/download failed (%s), falling back to mock", e)
            self._mock = True
            self._state = BackendReadyState.DEGRADED
            return

        worker_config = config.model_copy(update={"model_dir": str(model_dir)})
        self._worker = NativeTtsWorker(worker_config)
        self._state = BackendReadyState.WARMING_UP

    @property
    def backend_name(self) -> str:
        suffix = " (mock)" if self._mock else ""
        return f"{self._config.backend}{suffix}"

    @property
    def sample_rate(self) -> int:
        return self._engine_sample_rate

    @property
    def state(self) -> BackendReadyState:
        return self._state

    async def warmup(self) -> None:
        if self._mock:
            self._state = BackendReadyState.READY
            return
        text = _WARMUP_TEXT.get(self._config.backend, "hello")
        async with self._engine_lock:
            worker = self._require_worker()
            try:
                init_info = await worker.start()
                if init_info.get("sample_rate") is not None:
                    self._engine_sample_rate = int(init_info["sample_rate"])
                await worker.warmup(text)
            except asyncio.CancelledError:
                await self._fallback_to_mock_locked(worker)
                raise
            except Exception as e:
                logger.exception(
                    "TTS worker warmup failed (%s), falling back to mock", e
                )
                await self._fallback_to_mock_locked(worker)
                return
        self._state = BackendReadyState.READY

    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str],
        speed: float,
        pitch: float,
        volume: float,
    ) -> TtsResult:
        if not text or not text.strip():
            raise TtsInvalidText("empty text")

        if self._mock and not self._closed:
            return _mock_result(text, self.sample_rate)

        try:
            async with self._engine_lock:
                worker = self._require_worker()
                return await worker.synthesize(text)
        except Exception as e:
            logger.exception("TTS synthesize failed")
            raise TtsBackendUnavailable(str(e)) from e

    async def open_stream(
        self, voice_id: Optional[str], speed: float
    ) -> TtsStreamSession:
        loop = asyncio.get_running_loop()
        if self._mock and not self._closed:
            return _MockTtsStream(
                loop, self.sample_rate, self._config.stream.event_queue_size
            )
        async with self._engine_lock:
            self._require_worker()
        return _MatchaStream(
            self,
            loop,
            self.sample_rate,
            self._config.stream.event_queue_size,
            voice_id,
            speed,
        )

    def get_voices(self) -> List[VoiceInfo]:
        return _VOICES.get(self._config.backend, [])

    def get_models(self) -> List[ModelInfo]:
        entries = []
        for backend, voices in _VOICES.items():
            entries.append(
                ModelInfo(
                    id=backend,
                    name=f"Matcha-TTS {backend}",
                    capabilities=["tts", "streaming"],
                    languages=[v.language for v in voices],
                    sample_rate=self._engine_sample_rate,
                    loaded=backend == self._config.backend and self.is_ready,
                )
            )
        return entries

    def get_params(self) -> dict:
        return {
            "speed": self._config.speed,
            "pitch": self._config.pitch,
            "volume": self._config.volume,
            "emotion_strength": None,
        }

    def get_engine_config(self) -> dict:
        return {
            "threads": 1,
            "sample_rate": self._engine_sample_rate,
            "cache_policy": "process-isolated",
        }

    async def update_lexicon(self, entries: list[dict]) -> None:
        if self._mock or self._closed:
            return
        async with self._engine_lock:
            worker = self._require_worker()
            await worker.update_lexicon(entries)

    async def shutdown(self) -> None:
        async with self._engine_lock:
            self._closed = True
            self._state = BackendReadyState.IDLE
            self._mock = False
            worker, self._worker = self._worker, None
            if worker is not None:
                await worker.stop()

    async def _fallback_to_mock_locked(self, worker: NativeTtsWorker) -> None:
        if self._worker is worker:
            self._worker = None
        self._mock = True
        self._state = BackendReadyState.DEGRADED
        with contextlib.suppress(Exception):
            await worker.stop(kill=True)

    def _require_worker(self) -> NativeTtsWorker:
        if self._closed or self._worker is None:
            raise TtsBackendUnavailable("TTS backend is not loaded")
        return self._worker


# ---------------------------------------------------------------------------

def _ensure_model_assets(backend: str, model_dir, configured_models: list[dict]) -> None:
    assets = dict(_MODEL_ASSETS[backend])
    assets.update(_get_model_asset(configured_models, backend))
    ensure_remote_file(model_dir / assets["vocoder_name"], assets["vocoder_url"])
    ensure_archive_model(
        model_dir,
        url=assets["url"],
        archive_name=assets["archive_name"],
        required_paths=assets["required_paths"],
    )


def _get_model_asset(models: list[dict], model_id: str) -> dict:
    for item in models:
        if item.get("id") == model_id:
            return {key: value for key, value in item.items() if value}
    return {}


def _set_model_dir(engine_config, model_dir) -> None:
    model_dir_text = str(model_dir)
    if hasattr(engine_config, "model_dir"):
        engine_config.model_dir = model_dir_text
        return
    # Older spacemit_tts builds keep the native config behind this private wrapper.
    # Prefer the public model_dir attribute above and keep this fallback for compatibility.
    native_config = getattr(engine_config, "_config", None)
    if native_config is not None and hasattr(native_config, "model_dir"):
        native_config.model_dir = model_dir_text


def _mock_result(text: str, sample_rate: int) -> TtsResult:
    n_samples = sample_rate  # 1 秒静音
    return TtsResult(
        audio=np.zeros(n_samples, dtype=np.int16),
        sample_rate=sample_rate,
        duration_ms=1000.0,
        processing_ms=1.0,
        rtf=0.01,
    )


class _MockTtsStream(TtsStreamSession):
    """Mock 流式合成：每次 send_text → 产出 200ms 静音 chunk + 一个 metadata；complete → done。"""

    def __init__(self, loop, sample_rate: int, queue_size: int):
        super().__init__(loop, queue_size=queue_size)
        self._sample_rate = sample_rate
        self._chunk_samples = sample_rate // 5  # 200ms
        self._seq = 0
        self._timestamp_ms = 0.0

    async def start(self) -> None:
        # mock 不用预热
        return

    async def send_text(self, text: str) -> None:
        pcm = np.zeros(self._chunk_samples, dtype=np.int16).tobytes()
        self._enqueue_threadsafe(TtsAudioChunk(pcm=pcm, seq=self._seq))
        self._seq += 1
        self._timestamp_ms += 200.0
        # 可以附带一个 metadata（简单示范）
        # self._enqueue_threadsafe(TtsMetadata(text=text, timestamp_ms=self._timestamp_ms))

    async def complete(self) -> None:
        self._enqueue_threadsafe(TtsDone(duration_ms=self._timestamp_ms, rtf=0.01))
        self._enqueue_threadsafe(None)


class _MatchaStream(TtsStreamSession):
    """Gateway-level stream facade backed by the isolated worker.

    The native worker forwards native streaming callbacks as PCM chunks.
    This keeps the websocket contract while ensuring native allocations stay in the
    worker process.
    """

    def __init__(
        self,
        backend: MatchaBackend,
        loop,
        sample_rate: int,
        queue_size: int,
        voice_id: Optional[str],
        speed: float,
    ):
        super().__init__(loop, queue_size=queue_size)
        self._backend = backend
        self._sample_rate = sample_rate
        self._voice_id = voice_id
        self._speed = speed
        self._seq = 0
        self._total_ms = 0.0
        self._last_rtf = 0.0

    async def start(self) -> None:
        return

    async def send_text(self, text: str) -> None:
        if not text:
            return
        try:
            async with self._backend._engine_lock:
                worker = self._backend._require_worker()
                async for event in worker.stream_synthesize(text):
                    if event.get("type") == "audio":
                        pcm = np.asarray(event["audio"], dtype=np.int16).tobytes()
                        self._enqueue_threadsafe(TtsAudioChunk(pcm=pcm, seq=self._seq))
                        self._seq += 1
                        self._last_rtf = float(event.get("rtf") or 0.0)
                    elif event.get("type") == "done":
                        self._total_ms += float(event.get("duration_ms") or 0.0)
                        self._last_rtf = float(event.get("rtf") or self._last_rtf)
        except Exception as e:
            logger.exception("matcha stream synth failed")
            raise TtsBackendUnavailable(str(e)) from e

    async def complete(self) -> None:
        self._enqueue_threadsafe(
            TtsDone(duration_ms=self._total_ms, rtf=self._last_rtf)
        )
        self._enqueue_threadsafe(None)
