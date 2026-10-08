"""Kokoro TTS backend（基于 spacemit_tts 'kokoro' preset，24kHz 端到端合成）。

与 MatchaBackend 并列的独立后端。两者底层都用 spacemit_tts，但属于不同的 TTS 架构
（Kokoro 端到端；Matcha 声学模型 + vocoder），voice 列表与参数也不同，所以分文件实现。
共享的 ~40 行样板（_Mock、_Stream bridge）暂时容忍 duplicate，等第三个 spacemit_tts
后端出现时再抽基类。
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

import numpy as np

from ....app.settings import TtsConfig
from ....common.downloader import Artifact, ModelAssets
from ....common.errors import ModelLoadFailed, TtsBackendUnavailable, TtsInvalidText
from ....common.model_download import expand_path
from ....common.ready_state import BackendReadyState
from ....common.schemas import ModelInfo, VoiceInfo
from .base import (
    TtsAudioChunk,
    TtsBackend,
    TtsDone,
    TtsResult,
    TtsStreamSession,
)

logger = logging.getLogger(__name__)
logger_bridge = logging.getLogger(f"{__name__}._Bridge")

_BACKEND_ID = "kokoro"

# 与 model_zoo 的 Kokoro preset / 下载器保持一致：gateway 先把文件放到 SDK 会检查的目录，
# SDK 发现文件齐全就不再自己下载（tts/src/tts_presets.cpp、
# tts/src/backends/kokoro/kokoro_model_downloader.cpp::validateRequiredFiles）
_KOKORO_BASE_URL = "https://archive.spacemit.com/spacemit-ai/model_zoo/tts/kokoro"
_KOKORO_DEFAULT_DIR = "~/.cache/models/tts/kokoro-tts"
_KOKORO_DEFAULT_MODEL = "kokoro-v1.0-en"
_KOKORO_REQUIRED = {
    "kokoro-v1.0-en": (
        "kokoro-v1.0-en/kokoro-v1.0-en.q.onnx",
        "kokoro-v1.0-en/voices/af_heart.bin",
        "kokoro-v1.0-en/us_gold.json",
        "kokoro-v1.0-en/us_silver.json",
    ),
    "kokoro-v1.1-zh": (
        "kokoro-v1.1-zh/kokoro-v1.1-zh.q.onnx",
        "kokoro-v1.1-zh/tokenizer.json",
        "kokoro-v1.1-zh/config.json",
        "kokoro-v1.1-zh/voices/zf_001.npy",
        "kokoro-v1.1-zh/us_gold.json",
        "kokoro-v1.1-zh/us_silver.json",
    ),
}


def _preset_location() -> tuple[str, str]:
    """优先读已安装 SDK 的 preset（model_dir, model），读不到用与 SDK 一致的默认值。"""
    try:
        import spacemit_tts

        cfg = spacemit_tts.Config.preset(_BACKEND_ID)
        native = getattr(cfg, "_config", cfg)
        model_dir = getattr(cfg, "model_dir", None) or getattr(native, "model_dir", None)
        model = getattr(cfg, "model", None) or getattr(native, "model", None)
        return model_dir or _KOKORO_DEFAULT_DIR, model or _KOKORO_DEFAULT_MODEL
    except Exception:
        return _KOKORO_DEFAULT_DIR, _KOKORO_DEFAULT_MODEL


def model_assets(config: TtsConfig) -> Optional[ModelAssets]:
    model_dir, model = _preset_location()
    required = _KOKORO_REQUIRED.get(model)
    if required is None:
        # 旧版 SDK（如 spacemit-tts 1.0.4 的 kokoro-v1.0.q）从 HuggingFace 下载，布局不同，交给 SDK 自己下载
        return None
    return ModelAssets(_BACKEND_ID, [Artifact(
        f"{_KOKORO_BASE_URL}/{model}.tar.gz",
        expand_path(model_dir),
        archive=True,
        required=required,
    )])


_DEFAULT_SAMPLE_RATE = 24000

# Kokoro 声库初版：先列中英常用三条，待首次实际跑通后按真实 voice manifest 补齐
_VOICES: List[VoiceInfo] = [
    VoiceInfo(id="zf_xiaobei", name="小贝（中文女声）", language="zh", gender="female"),
    VoiceInfo(id="zm_yunxi",   name="云希（中文男声）", language="zh", gender="male"),
    VoiceInfo(id="af_heart",   name="Heart (English female)", language="en", gender="female"),
]


class KokoroBackend(TtsBackend):
    def __init__(self, config: TtsConfig):
        self._config = config
        self._mock = False
        self._engine = None
        self._engine_lock = asyncio.Lock()
        self._closed = False
        self._state = BackendReadyState.INITIALIZING

        try:
            import spacemit_tts  # noqa: F401
        except ImportError:
            logger.warning("spacemit_tts not installed → Kokoro mock backend")
            self._mock = True
            self._state = BackendReadyState.DEGRADED
            self._engine_sample_rate = config.sample_rate or _DEFAULT_SAMPLE_RATE
            return

        try:
            import spacemit_tts
            engine_config = spacemit_tts.Config.preset(_BACKEND_ID)
            if config.sample_rate is not None:
                engine_config.sample_rate = config.sample_rate
            engine_config.speed = config.speed
            self._engine = spacemit_tts.Engine(engine_config)
            self._engine_sample_rate = int(engine_config.sample_rate)
            self._state = BackendReadyState.WARMING_UP
        except Exception as e:
            # SDK 已导入成功，初始化失败要如实报错，不能用 mock 假结果冒充成功
            logger.exception("Kokoro engine init failed: %s", e)
            raise ModelLoadFailed(f"Kokoro engine init failed: {e}") from e
            self._engine_sample_rate = config.sample_rate or _DEFAULT_SAMPLE_RATE

    @property
    def backend_name(self) -> str:
        suffix = " (mock)" if self._mock else ""
        return f"{_BACKEND_ID}{suffix}"

    @property
    def sample_rate(self) -> int:
        return self._engine_sample_rate

    @property
    def state(self) -> BackendReadyState:
        return self._state

    async def warmup(self) -> None:
        if not self._mock:
            async with self._engine_lock:
                self._require_engine()
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
                engine = self._require_engine()
                raw = await self._run_engine_call(engine.synthesize, text)
        except Exception as e:
            logger.exception("Kokoro synthesize failed")
            raise TtsBackendUnavailable(str(e)) from e

        if not raw.is_success:
            raise TtsBackendUnavailable(
                f"synthesize failed: {getattr(raw, 'message', 'unknown error')}"
            )

        return TtsResult(
            audio=np.asarray(raw.audio_int16, dtype=np.int16),
            sample_rate=int(raw.sample_rate),
            duration_ms=float(raw.duration_ms),
            processing_ms=float(raw.processing_time_ms),
            rtf=float(raw.rtf),
        )

    async def open_stream(
        self, voice_id: Optional[str], speed: float
    ) -> TtsStreamSession:
        loop = asyncio.get_running_loop()
        if self._mock and not self._closed:
            return _MockTtsStream(
                loop, self.sample_rate, self._config.stream.event_queue_size
            )
        async with self._engine_lock:
            self._require_engine()
        return _KokoroStream(
            self, loop, self.sample_rate, self._config.stream.event_queue_size
        )

    def get_voices(self) -> List[VoiceInfo]:
        return list(_VOICES)

    def get_models(self) -> List[ModelInfo]:
        return [
            ModelInfo(
                id=_BACKEND_ID,
                name="Kokoro-TTS",
                capabilities=["tts", "streaming"],
                languages=sorted({v.language for v in _VOICES}),
                sample_rate=self._engine_sample_rate,
                loaded=self._config.backend == _BACKEND_ID and self.is_ready,
            )
        ]

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
            "cache_policy": None,
        }

    async def shutdown(self) -> None:
        async with self._engine_lock:
            self._closed = True
            self._state = BackendReadyState.IDLE
            self._mock = False
            self._engine = None

    def _require_engine(self):
        if self._closed or self._engine is None:
            raise TtsBackendUnavailable("TTS backend is not loaded")
        return self._engine

    async def _run_engine_call(self, func, *args):
        task = asyncio.create_task(asyncio.to_thread(func, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            except Exception:
                logger.debug("Kokoro native call failed after cancellation", exc_info=True)
            raise


# ---------------------------------------------------------------------------

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
    """Mock 流式合成：每次 send_text → 产出 200ms 静音 chunk；complete → done。"""

    def __init__(self, loop, sample_rate: int, queue_size: int):
        super().__init__(loop, queue_size=queue_size)
        self._sample_rate = sample_rate
        self._chunk_samples = sample_rate // 5  # 200ms
        self._seq = 0
        self._timestamp_ms = 0.0

    async def start(self) -> None:
        return

    async def send_text(self, text: str) -> None:
        pcm = np.zeros(self._chunk_samples, dtype=np.int16).tobytes()
        self._enqueue_threadsafe(TtsAudioChunk(pcm=pcm, seq=self._seq))
        self._seq += 1
        self._timestamp_ms += 200.0

    async def complete(self) -> None:
        self._enqueue_threadsafe(TtsDone(duration_ms=self._timestamp_ms, rtf=0.01))
        self._enqueue_threadsafe(None)


class _KokoroStream(TtsStreamSession):
    """真 SDK 流式合成，同 _MatchaStream 协议（spacemit_tts.TtsCallback 回调链）。"""

    def __init__(self, backend: KokoroBackend, loop, sample_rate: int, queue_size: int):
        super().__init__(loop, queue_size=queue_size)
        self._backend = backend
        self._sample_rate = sample_rate
        self._seq = 0
        self._total_ms = 0.0
        self._last_rtf = 0.0
        self._error_message: Optional[str] = None

    async def start(self) -> None:
        return

    async def send_text(self, text: str) -> None:
        if not text:
            return
        bridge = self._make_bridge()
        try:
            async with self._backend._engine_lock:
                engine = self._backend._require_engine()
                await self._backend._run_engine_call(
                    engine.synthesize_streaming, text, bridge
                )
        except Exception as e:
            logger.exception("kokoro stream synth failed")
            raise TtsBackendUnavailable(str(e)) from e
        if self._error_message:
            err, self._error_message = self._error_message, None
            raise TtsBackendUnavailable(err)

    def _make_bridge(self):
        import spacemit_tts

        outer = self

        class _Bridge(spacemit_tts.TtsCallback):
            def on_open(self) -> None:
                logger_bridge.debug("kokoro on_open")

            def on_event(self, result) -> None:
                try:
                    arr = np.asarray(result.get_audio_int16(), dtype=np.int16)
                    pcm = arr.tobytes()
                except Exception:
                    logger_bridge.debug(
                        "kokoro on_event decode failed", exc_info=True
                    )
                    return

                try:
                    dur = float(result.get_duration_ms() or 0)
                    rtf = float(result.get_rtf() or 0.0)
                except Exception:
                    dur = 0.0
                    rtf = 0.0

                logger_bridge.debug(
                    "kokoro on_event seq=%d dur=%.1fms rtf=%.3f bytes=%d",
                    outer._seq, dur, rtf, len(pcm),
                )
                outer._enqueue_threadsafe(
                    TtsAudioChunk(pcm=pcm, seq=outer._seq)
                )
                outer._seq += 1
                outer._total_ms += dur
                outer._last_rtf = rtf

            def on_complete(self) -> None:
                logger_bridge.debug("kokoro on_complete")

            def on_error(self, message: str) -> None:
                logger_bridge.error("kokoro on_error: %s", message)
                outer._error_message = str(message) if message else "kokoro tts error"

            def on_close(self) -> None:
                logger_bridge.debug("kokoro on_close")

        return _Bridge()

    async def complete(self) -> None:
        self._enqueue_threadsafe(
            TtsDone(duration_ms=self._total_ms, rtf=self._last_rtf)
        )
        self._enqueue_threadsafe(None)
