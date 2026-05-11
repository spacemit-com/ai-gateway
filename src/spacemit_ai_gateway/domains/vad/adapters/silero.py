"""Silero VAD backend（基于 spacemit_vad SDK）。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional

import numpy as np

from ....app.settings import VadConfig
from ....common.errors import VadBackendUnavailable, VadInvalidAudio
from ....common.ready_state import BackendReadyState
from .base import Segment, VadAnalysis, VadBackend, VadEvent, VadStreamSession

logger = logging.getLogger(__name__)


class SileroBackend(VadBackend):
    def __init__(self, config: VadConfig):
        self._config = config
        self._mock = False
        self._engine = None
        self._state = BackendReadyState.INITIALIZING

        try:
            import spacemit_vad  # noqa: F401
        except ImportError:
            logger.warning("spacemit_vad not installed → VAD mock backend")
            self._mock = True
            self._state = BackendReadyState.DEGRADED
            return

        try:
            import spacemit_vad
            engine_config = spacemit_vad.VadConfig.preset("silero")
            engine_config.sample_rate = config.sample_rate
            engine_config.trigger_threshold = config.trigger_threshold
            engine_config.stop_threshold = config.stop_threshold
            engine_config.min_speech_duration_ms = config.min_speech_ms
            engine_config.min_silence_duration_ms = config.max_silence_ms
            self._engine = spacemit_vad.VadEngine(engine_config)
            self._state = BackendReadyState.WARMING_UP
        except Exception as e:
            logger.exception("VAD engine init failed (%s), falling back to mock", e)
            self._mock = True
            self._state = BackendReadyState.DEGRADED

    @property
    def backend_name(self) -> str:
        suffix = " (mock)" if self._mock else ""
        return f"silero{suffix}"

    @property
    def state(self) -> BackendReadyState:
        return self._state

    async def warmup(self) -> None:
        self._state = BackendReadyState.READY

    async def analyze(self, audio: bytes, sample_rate: int) -> VadAnalysis:
        if not audio:
            raise VadInvalidAudio("empty audio payload")

        if self._mock:
            return VadAnalysis(
                is_speech=True, probability=0.8, smoothed_probability=0.8, processing_ms=1.0
            )

        start = time.perf_counter()
        try:
            max_prob, any_speech, last_smoothed = await asyncio.to_thread(
                self._analyze_sync, audio, sample_rate
            )
        except Exception as e:
            logger.exception("VAD detect failed")
            raise VadBackendUnavailable(str(e)) from e
        processing_ms = (time.perf_counter() - start) * 1000

        return VadAnalysis(
            is_speech=any_speech,
            probability=max_prob,
            smoothed_probability=last_smoothed,
            processing_ms=processing_ms,
        )

    def _analyze_sync(
        self, audio: bytes, sample_rate: int
    ) -> tuple[float, bool, Optional[float]]:
        """切 30ms 帧逐帧 detect——Silero 的 detect 是单帧接口，
        把整段 PCM 一次塞进去 SDK 只看某一截，probability 无意义。"""
        import spacemit_vad

        frame_ms = 30
        frame_bytes = int(sample_rate * frame_ms / 1000) * 2

        max_prob = 0.0
        any_speech = False
        last_smoothed: Optional[float] = None

        for i in range(0, len(audio), frame_bytes):
            frame = audio[i : i + frame_bytes]
            if len(frame) < frame_bytes:
                break
            frame_np = np.frombuffer(frame, dtype=np.int16)
            raw = self._engine.detect(frame_np, sample_rate)
            if raw.state == spacemit_vad.VadState.SPEECH:
                any_speech = True
            p = float(raw.probability)
            if p > max_prob:
                max_prob = p
            smoothed = getattr(raw, "smoothed_probability", None)
            if smoothed is not None:
                last_smoothed = float(smoothed)

        return max_prob, any_speech, last_smoothed

    async def segment(
        self, audio: bytes, sample_rate: int
    ) -> tuple[List[Segment], float]:
        if not audio:
            raise VadInvalidAudio("empty audio payload")

        duration_ms = len(audio) / max(sample_rate, 1) / 2 * 1000  # 16-bit PCM

        if self._mock:
            return (
                [Segment(start_ms=0.0, end_ms=duration_ms, confidence=0.9)],
                duration_ms,
            )

        try:
            segments = await asyncio.to_thread(self._segment_sync, audio, sample_rate)
        except Exception as e:
            logger.exception("VAD segment failed")
            raise VadBackendUnavailable(str(e)) from e
        return segments, duration_ms

    def _segment_sync(self, audio: bytes, sample_rate: int) -> List[Segment]:
        import spacemit_vad

        frame_ms = 30
        frame_bytes = int(sample_rate * frame_ms / 1000) * 2

        segments: List[Segment] = []
        current: Optional[Segment] = None
        t_ms = 0.0

        for i in range(0, len(audio), frame_bytes):
            frame = audio[i : i + frame_bytes]
            if len(frame) < frame_bytes:
                break
            frame_np = np.frombuffer(frame, dtype=np.int16)
            raw = self._engine.detect(frame_np, sample_rate)
            is_speech = raw.state == spacemit_vad.VadState.SPEECH
            p = float(raw.probability)
            if is_speech:
                if current is None:
                    current = Segment(start_ms=t_ms, end_ms=t_ms, confidence=p)
                elif p > current.confidence:
                    current.confidence = p
            else:
                if current is not None:
                    current.end_ms = t_ms
                    segments.append(current)
                    current = None
            t_ms += frame_ms

        if current is not None:
            current.end_ms = t_ms
            segments.append(current)
        return segments

    async def open_stream(self, sample_rate: int) -> VadStreamSession:
        loop = asyncio.get_running_loop()
        return _SileroStream(
            backend=self,
            loop=loop,
            sample_rate=sample_rate,
            queue_size=self._config.stream.event_queue_size,
            mock=self._mock,
        )

    def get_params(self) -> dict:
        return {
            "trigger_threshold": self._config.trigger_threshold,
            "stop_threshold": self._config.stop_threshold,
            "min_speech_ms": self._config.min_speech_ms,
            "max_silence_ms": self._config.max_silence_ms,
            "sample_rate": self._config.sample_rate,
        }

    def get_audio_config(self) -> dict:
        return {
            "sample_rate": self._config.sample_rate,
            "bit_depth": 16,
            "denoise": False,
        }

    def get_engine_config(self) -> dict:
        return {
            "threads": 1,
            "npu_priority": None,
            "memory_limit": None,
        }


class _SileroStream(VadStreamSession):
    def __init__(self, backend: SileroBackend, loop, sample_rate, queue_size, mock: bool):
        super().__init__(loop, queue_size=queue_size)
        self._backend = backend
        self._sample_rate = sample_rate
        self._mock = mock
        self._frame_ms = 30
        self._timestamp_ms = 0.0
        self._last_speech: Optional[bool] = None

    async def start(self) -> None:
        return

    async def send_audio(self, chunk: bytes) -> None:
        if self._mock:
            # Mock: 交替 speech/silence
            is_speech = (int(self._timestamp_ms) // 300) % 2 == 0
            prob = 0.85 if is_speech else 0.1
        else:
            try:
                analysis = await self._backend.analyze(chunk, self._sample_rate)
            except Exception:
                logger.exception("stream analyze failed")
                return
            is_speech = analysis.is_speech
            prob = analysis.probability

        event: Optional[VadEvent] = None
        if self._last_speech is None:
            event = VadEvent(
                event="speech" if is_speech else "silence",
                probability=prob,
                timestamp_ms=self._timestamp_ms,
            )
        elif is_speech and not self._last_speech:
            event = VadEvent(
                event="speech_start", probability=prob, timestamp_ms=self._timestamp_ms
            )
        elif not is_speech and self._last_speech:
            event = VadEvent(
                event="speech_end", probability=prob, timestamp_ms=self._timestamp_ms
            )

        if event is not None:
            self._enqueue_threadsafe(event)

        self._last_speech = is_speech
        self._timestamp_ms += self._frame_ms

    async def stop(self) -> None:
        self._enqueue_threadsafe(None)
