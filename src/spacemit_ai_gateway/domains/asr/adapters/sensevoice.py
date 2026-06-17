"""SenseVoice backend（基于 spacemit_asr SDK）。

支持 mock 降级：
- 模型缺失 → 下载到 model_dir 后初始化
- SDK ImportError 或 Engine 初始化 Exception → 降级 mock + exception 日志
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

import numpy as np

from ....app.settings import AsrConfig
from ....common.errors import AsrBackendUnavailable, AsrInvalidAudio
from ....common.model_download import ensure_archive_model, expand_path
from ....common.ready_state import BackendReadyState
from ....common.schemas import ModelInfo
from .base import (
    DEFAULT_SAMPLE_RATE,
    AsrBackend,
    AsrEvent,
    AsrStreamSession,
    RecognitionResult,
    build_pcm16_silence,
)

logger = logging.getLogger(__name__)
logger_bridge = logging.getLogger(f"{__name__}._Bridge")

_DEFAULT_MODEL_DIR = "~/.cache/models/asr/sensevoice"
_MODEL_URL = "https://archive.spacemit.com/spacemit-ai/model_zoo/asr/sensevoice.tar.gz"
_REQUIRED_MODEL_FILES = (
    "model_quant_optimized.onnx",
    "tokens.txt",
    "am.mvn",
    "sensevoice_decoder_model.onnx",
)


def _lang_from_str(language: str):
    """映射 "zh"/"en"/... 字符串到 spacemit_asr.Language enum。"""
    import spacemit_asr

    table = {
        "auto": spacemit_asr.Language.AUTO,
        "zh": spacemit_asr.Language.ZH,
        "en": spacemit_asr.Language.EN,
        "ja": spacemit_asr.Language.JA,
        "ko": spacemit_asr.Language.KO,
        "yue": spacemit_asr.Language.YUE,
    }
    return table.get((language or "auto").lower(), spacemit_asr.Language.AUTO)


def _extract_emotion(raw) -> Optional[str]:
    emotion = getattr(raw, "emotion", None)
    if emotion:
        return str(emotion)

    sentences = getattr(raw, "sentences", None) or []
    for sentence in sentences:
        if isinstance(sentence, dict):
            emotion = sentence.get("emotion")
        else:
            emotion = getattr(sentence, "emotion", None)
        if emotion:
            return str(emotion)
    return None


class SenseVoiceBackend(AsrBackend):
    def __init__(self, config: AsrConfig):
        self._config = config
        self._mock = False
        self._engine = None
        self._state = BackendReadyState.INITIALIZING
        self._emotion_enabled = False

        model_dir = expand_path(config.model_dir or _DEFAULT_MODEL_DIR)
        asset = _get_model_asset(config.models, config.backend)
        try:
            ensure_archive_model(
                model_dir,
                url=asset.get("url") or _MODEL_URL,
                archive_name=asset.get("archive_name") or "sensevoice.tar.gz",
                archive_subdir=asset.get("archive_subdir") or "sensevoice",
                required_paths=_REQUIRED_MODEL_FILES,
            )
        except Exception as e:
            logger.exception("ASR model check/download failed (%s), falling back to mock", e)
            self._mock = True
            self._state = BackendReadyState.DEGRADED
            return

        try:
            import spacemit_asr
        except ImportError as e:
            logger.warning("spacemit_asr unavailable (%s) → ASR mock backend", e)
            self._mock = True
            self._state = BackendReadyState.DEGRADED
            return

        try:
            engine_config = spacemit_asr.Config(model_dir=str(model_dir))
            engine_config.language = _lang_from_str(config.language)
            engine_config.punctuation_enabled = config.punctuation
            engine_config.provider = config.provider
            if hasattr(engine_config, "enable_emotion"):
                # Keep metadata available for per-request emotion toggles. The
                # public response still only exposes emotion when requested.
                engine_config.enable_emotion = True
                self._emotion_enabled = True
            elif config.enable_emotion:
                raise RuntimeError("spacemit-asr>=1.0.2 is required for enable_emotion")
            self._engine = spacemit_asr.Engine(engine_config)
            self._engine.initialize()
            self._state = BackendReadyState.WARMING_UP
        except Exception as e:
            logger.exception("ASR engine init failed (%s), falling back to mock", e)
            self._mock = True
            self._state = BackendReadyState.DEGRADED

    @property
    def backend_name(self) -> str:
        suffix = " (mock)" if self._mock else ""
        return f"sensevoice{suffix}"

    @property
    def state(self) -> BackendReadyState:
        return self._state

    @property
    def emotion_enabled(self) -> bool:
        return self._emotion_enabled and not self._mock

    async def warmup(self) -> None:
        if self._mock:
            self._state = BackendReadyState.READY
            return
        audio = build_pcm16_silence(self._config.warmup_audio_ms)
        if audio:
            await self.recognize(
                audio=audio,
                sample_rate=DEFAULT_SAMPLE_RATE,
                language=self._config.language,
                punctuation=self._config.punctuation,
            )
        self._state = BackendReadyState.READY

    async def recognize(
        self,
        audio: bytes,
        sample_rate: int,
        language: str,
        punctuation: bool,
        hotwords: Optional[List[str]] = None,
        enable_emotion: bool = False,
    ) -> RecognitionResult:
        if not audio:
            raise AsrInvalidAudio("empty audio payload")

        if self._mock:
            return _mock_result(audio, sample_rate, language)

        try:
            if hotwords and not self._mock:
                await asyncio.to_thread(self._engine.update_hotwords, hotwords)

            # SDK recognize 只接受 numpy 一维数组（int16 或 float32）
            samples = _pcm16_bytes_to_model_samples(audio, sample_rate)
            raw = await asyncio.to_thread(self._engine.recognize, samples)
        except Exception as e:
            logger.exception("ASR recognize failed")
            raise AsrBackendUnavailable(str(e)) from e

        if self._state is not BackendReadyState.READY:
            self._state = BackendReadyState.READY

        return RecognitionResult(
            text=raw.text,
            sentences=[],  # SDK Result.sentences 结构未对齐，暂留空；日后按真实字段解析
            duration_ms=float(getattr(raw, "audio_duration_ms", 0)),
            processing_ms=float(getattr(raw, "processing_time_ms", 0)),
            rtf=float(getattr(raw, "rtf", 0.0)),
            language=language,
            emotion=_extract_emotion(raw) if enable_emotion else None,
        )

    async def create_stream(
        self,
        sample_rate: int,
        language: str,
        partial: bool,
        enable_emotion: bool = False,
    ) -> AsrStreamSession:
        loop = asyncio.get_running_loop()
        if self._mock:
            return _MockStream(loop, queue_size=self._config.stream.event_queue_size)
        return _SenseVoiceStream(
            self._engine, loop, sample_rate, language, partial, enable_emotion,
            queue_size=self._config.stream.event_queue_size,
        )

    def get_supported_languages(self) -> List[str]:
        return ["zh", "en", "ja", "ko", "yue", "auto"]

    def get_models(self) -> List[ModelInfo]:
        return [
            ModelInfo(
                id="sensevoice",
                name="SenseVoice",
                capabilities=["multilingual", "streaming", "emotion"],
                languages=self.get_supported_languages(),
                sample_rate=16000,
                loaded=self._config.backend == "sensevoice" and self.is_ready,
            ),
        ]

    def get_params(self) -> dict:
        return {
            "language": self._config.language,
            "punctuation": self._config.punctuation,
            "hotword_weight": None,
            "itn": None,
            "enable_emotion": self._config.enable_emotion,
        }

    def get_audio_config(self) -> dict:
        return {
            "sample_rate": 16000,
            "vad_threshold": None,
            "denoise": False,
            "agc": False,
        }

    def get_engine_config(self) -> dict:
        return {
            "num_threads": 1,
            "device": self._config.provider,
            "power_mode": None,
        }


# ------------------------------------------------------------
# Mock helpers
# ------------------------------------------------------------

def _get_model_asset(models: list[dict], model_id: str) -> dict:
    for item in models:
        if item.get("id") == model_id:
            return item
    return {}


def _pcm16_bytes_to_model_samples(audio: bytes, sample_rate: int) -> np.ndarray:
    if len(audio) % 2 != 0:
        audio = audio[:-1]
    samples = np.frombuffer(audio, dtype=np.int16)
    if sample_rate <= 0 or sample_rate == DEFAULT_SAMPLE_RATE or samples.size == 0:
        return samples
    return _resample_pcm16(samples, sample_rate, DEFAULT_SAMPLE_RATE)


def _resample_pcm16(
    samples: np.ndarray,
    source_rate: int,
    target_rate: int,
) -> np.ndarray:
    if source_rate <= 0 or source_rate == target_rate or samples.size <= 1:
        return samples

    target_size = max(1, int(round(samples.size * target_rate / source_rate)))
    source_positions = np.arange(samples.size, dtype=np.float64)
    target_positions = np.linspace(0, samples.size - 1, num=target_size, dtype=np.float64)
    resampled = np.interp(target_positions, source_positions, samples.astype(np.float32))
    return np.clip(
        np.rint(resampled),
        np.iinfo(np.int16).min,
        np.iinfo(np.int16).max,
    ).astype(np.int16)


def _mock_result(audio: bytes, sample_rate: int, language: str) -> RecognitionResult:
    duration_ms = len(audio) / max(sample_rate, 1) / 2 * 1000  # 16-bit PCM 估算
    return RecognitionResult(
        text="[mock] 识别结果",
        sentences=[],
        duration_ms=duration_ms,
        processing_ms=1.0,
        rtf=0.01,
        language=language,
    )


class _MockStream(AsrStreamSession):
    """Mock 流式：start → ready；每 send_audio 推一个 partial；stop → final。"""

    def __init__(self, loop, queue_size: int):
        super().__init__(loop, queue_size=queue_size)
        self._chunks = 0

    async def start(self) -> None:
        self._enqueue_threadsafe(AsrEvent(type="ready"))

    async def send_audio(self, chunk: bytes) -> None:
        self._chunks += 1
        self._enqueue_threadsafe(
            AsrEvent(type="partial", text=f"[mock partial #{self._chunks}]")
        )

    async def stop(self) -> RecognitionResult:
        result = RecognitionResult(
            text="[mock] 最终识别结果",
            duration_ms=float(self._chunks * 30),
            processing_ms=1.0,
            rtf=0.01,
        )
        self._enqueue_threadsafe(
            AsrEvent(
                type="final",
                text=result.text,
                duration_ms=result.duration_ms,
                rtf=result.rtf,
            )
        )
        self._enqueue_threadsafe(None)
        return result


class _SenseVoiceStream(AsrStreamSession):
    """真 SDK 流式会话。

    SDK 契约（见 spacemit_asr.AsrCallback）：
    - engine.start(callback=<AsrCallback 实例>)—— callback 必须是子类实例
    - 回调链：on_open → on_event*(is_final=False/True) → on_complete → on_close
    - stop() 强同步：返回前 on_close 已执行完；但跨线程 enqueue 还在 loop 排队
    """

    def __init__(
        self,
        engine,
        loop,
        sample_rate,
        language,
        partial,
        enable_emotion: bool,
        queue_size: int,
    ):
        super().__init__(loop, queue_size=queue_size)
        self._engine = engine
        self._sample_rate = sample_rate
        self._language = language
        self._partial = partial
        self._enable_emotion = enable_emotion
        self._started = False
        self._final_result: Optional[RecognitionResult] = None
        self._saw_final = False
        self._error_message: Optional[str] = None
        self._close_event = asyncio.Event()
        self._bridge = self._make_bridge()

    def _make_bridge(self):
        import spacemit_asr

        outer = self

        class _Bridge(spacemit_asr.AsrCallback):
            def on_open(self) -> None:
                logger_bridge.debug("asr on_open")
                outer._enqueue_threadsafe(AsrEvent(type="ready"))

            def on_event(self, result) -> None:
                try:
                    is_final = bool(getattr(result, "is_final", False))
                    text = getattr(result, "text", "") or ""
                    duration_ms = float(getattr(result, "audio_duration_ms", 0) or 0)
                    processing_ms = float(
                        getattr(result, "processing_time_ms", 0) or 0
                    )
                    rtf = float(getattr(result, "rtf", 0.0) or 0.0)
                    emotion = _extract_emotion(result) if outer._enable_emotion else None
                except Exception:
                    logger_bridge.debug("asr on_event parse failed", exc_info=True)
                    return

                logger_bridge.debug(
                    "asr on_event is_final=%s text=%r", is_final, text
                )

                event_type = "final" if is_final else "partial"
                outer._enqueue_threadsafe(
                    AsrEvent(
                        type=event_type,
                        text=text,
                        duration_ms=duration_ms,
                        rtf=rtf,
                        extra={"emotion": emotion} if emotion else {},
                    )
                )
                if is_final:
                    outer._saw_final = True

                # SenseVoice 是句级模型，is_final 可能恒 False 但每个 on_event 都是有效句子。
                # 无论 is_final 如何都累加到 _final_result；on_close 前若从未见过 final
                # 再补发一个 session-级 final 事件（见 on_close）。
                if text:
                    if outer._final_result is None:
                        outer._final_result = RecognitionResult(
                            text=text,
                            duration_ms=duration_ms,
                            processing_ms=processing_ms,
                            rtf=rtf,
                            language=outer._language,
                            emotion=emotion,
                        )
                    else:
                        outer._final_result.text += text
                        outer._final_result.duration_ms += duration_ms
                        outer._final_result.processing_ms += processing_ms
                        outer._final_result.rtf = rtf
                        if emotion and not outer._final_result.emotion:
                            outer._final_result.emotion = emotion

            def on_complete(self) -> None:
                logger_bridge.debug("asr on_complete")

            def on_error(self, result) -> None:
                message = getattr(result, "message", None) or str(result)
                logger_bridge.error("asr on_error: %s", message)
                outer._error_message = message
                outer._enqueue_threadsafe(AsrEvent(type="error", text=message))

            def on_close(self) -> None:
                logger_bridge.debug("asr on_close")
                # 若 SDK 从未发 is_final=True（SenseVoice 常见），补发一个 session final
                if (
                    not outer._saw_final
                    and outer._final_result is not None
                    and outer._final_result.text
                ):
                    outer._enqueue_threadsafe(
                        AsrEvent(
                            type="final",
                            text=outer._final_result.text,
                            duration_ms=outer._final_result.duration_ms,
                            rtf=outer._final_result.rtf,
                            extra={"emotion": outer._final_result.emotion}
                            if outer._final_result.emotion
                            else {},
                        )
                    )
                outer._loop.call_soon_threadsafe(outer._close_event.set)
                outer._enqueue_threadsafe(None)

        return _Bridge()

    async def start(self) -> None:
        try:
            await asyncio.to_thread(self._engine.start, callback=self._bridge)
            self._started = True
        except Exception as e:
            logger.exception("asr stream start failed")
            raise AsrBackendUnavailable(str(e)) from e

    async def send_audio(self, chunk: bytes) -> None:
        # TODO(backpressure): engine.send_audio_frame 需确认是否阻塞（内部 ring buffer 满 → 等）。
        # 若非阻塞，asyncio.to_thread 在 ThreadPoolExecutor 队列里堆积会把 WS 接收端喂爆。
        # 骨架期按 SDK 阻塞假设处理，压测阶段再验证。
        if not self._started:
            raise AsrBackendUnavailable("stream not started")
        try:
            await asyncio.to_thread(self._engine.send_audio_frame, chunk)
        except Exception as e:
            logger.exception("asr send_audio failed")
            raise AsrBackendUnavailable(str(e)) from e

    async def stop(self) -> RecognitionResult:
        if not self._started:
            raise AsrBackendUnavailable("stream not started")
        try:
            # SDK 强同步：返回前 on_event(final) / on_complete / on_close 都已触发
            await asyncio.to_thread(self._engine.stop)
        except Exception as e:
            logger.exception("asr stream stop failed")
            raise AsrBackendUnavailable(str(e)) from e
        finally:
            self._started = False

        # 等 on_close 的 call_soon_threadsafe 被事件循环处理完，
        # 确保 pump task 能拿到 final / None 再被 handler cancel
        try:
            await asyncio.wait_for(self._close_event.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            logger.warning("asr on_close not observed within 1s")

        if self._error_message:
            raise AsrBackendUnavailable(self._error_message)

        return self._final_result or RecognitionResult(
            text="",
            duration_ms=0.0,
            processing_ms=0.0,
            rtf=0.0,
            language=self._language,
        )
