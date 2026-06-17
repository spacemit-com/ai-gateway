"""Qwen3-ASR backend（HTTP 调 llama-server）。

协议：OpenAI chat/completions multimodal。audio 按当前 AsrBackend 契约是 PCM16 raw
@ sample_rate（与 SenseVoice 对齐，见 sensevoice.py 的 np.frombuffer(..., int16)），
本 backend 包 WAV header → base64 → POST /v1/chat/completions。
流式：用 BufferedStream，累积音频 stop 时一次性调 recognize，发一个 final。
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
import wave
from typing import List, Optional

import httpx

from ....app.settings import AsrConfig
from ....common.errors import AsrBackendUnavailable, AsrInvalidAudio
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


_LANG_PROMPT = {
    "zh":  "Chinese",
    "en":  "English",
    "ja":  "Japanese",
    "ko":  "Korean",
    "yue": "Chinese",
}


def _pcm16_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """把 PCM16 mono raw bytes 包成 WAV bytes（用于 llama-server 的 input_audio.data）。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


class Qwen3AsrBackend(AsrBackend):
    def __init__(self, config: AsrConfig):
        self._config = config
        # endpoint 是一条完整 URL，不拆 base_url + path，避免 llama-server 路径拼接出错
        self._endpoint = config.qwen3.endpoint
        self._client = httpx.AsyncClient(timeout=config.qwen3.timeout)
        # HTTP 后端总是可以启动；真实连通性在第一次 recognize 时验证
        self._state = BackendReadyState.WARMING_UP

    @property
    def backend_name(self) -> str:
        return "qwen3-asr"

    @property
    def state(self) -> BackendReadyState:
        return self._state

    async def warmup(self) -> None:
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

        wav_bytes = _pcm16_to_wav(audio, sample_rate)
        b64 = base64.b64encode(wav_bytes).decode("ascii")
        lang_prompt = _LANG_PROMPT.get((language or "auto").lower(), "auto")

        payload = {
            "model": self._config.qwen3.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "input_audio",
                     "input_audio": {"data": b64, "format": "wav"}},
                    {"type": "text",
                     "text": f"language {lang_prompt}<asr_text>"},
                ],
            }],
            "max_tokens": 512,
            "temperature": 0,
        }

        # PCM16 mono 时长：bytes / 2 / sample_rate * 1000
        duration_ms = len(audio) / 2 / max(sample_rate, 1) * 1000.0
        t0 = time.perf_counter()
        try:
            response = await self._client.post(self._endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as e:
            raise AsrBackendUnavailable(f"qwen3-asr timeout: {e}") from e
        except httpx.HTTPError as e:
            raise AsrBackendUnavailable(f"qwen3-asr HTTP error: {e}") from e
        except ValueError as e:  # JSON decode
            raise AsrBackendUnavailable(f"qwen3-asr invalid JSON: {e}") from e

        try:
            message = data["choices"][0]["message"]
            content = message.get("content", "")
        except (KeyError, IndexError, TypeError) as e:
            raise AsrBackendUnavailable(
                f"qwen3-asr unexpected response shape: {data!r}"
            ) from e

        # content 有两种形态：字符串，或 [{"type":"text","text":"..."}] 列表
        if isinstance(content, list):
            text = "".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        else:
            text = str(content or "")
        text = text.strip()

        processing_ms = (time.perf_counter() - t0) * 1000.0
        rtf = processing_ms / duration_ms if duration_ms > 0 else 0.0

        if self._state is not BackendReadyState.READY:
            self._state = BackendReadyState.READY

        return RecognitionResult(
            text=text,
            duration_ms=duration_ms,
            processing_ms=processing_ms,
            rtf=rtf,
            language=language,
        )

    async def create_stream(
        self,
        sample_rate: int,
        language: str,
        partial: bool,
        enable_emotion: bool = False,
    ) -> AsrStreamSession:
        loop = asyncio.get_running_loop()
        return _Qwen3BufferedStream(
            backend=self,
            loop=loop,
            sample_rate=sample_rate,
            language=language,
            queue_size=self._config.stream.event_queue_size,
        )

    def get_supported_languages(self) -> List[str]:
        return ["zh", "en"]

    def get_models(self) -> List[ModelInfo]:
        return [
            ModelInfo(
                id="qwen3-asr",
                name="Qwen3-ASR",
                capabilities=["multilingual"],
                languages=self.get_supported_languages(),
                loaded=self._config.backend == "qwen3-asr" and self.is_ready,
            ),
        ]

    def get_params(self) -> dict:
        return {
            "language": "zh",
            "punctuation": True,
            "hotword_weight": None,
            "itn": None,
            "enable_emotion": False,
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
            "device": "http",
            "power_mode": None,
        }

    async def shutdown(self) -> None:
        try:
            await self._client.aclose()
        except Exception:
            logger.debug("qwen3 client close failed", exc_info=True)


class _Qwen3BufferedStream(AsrStreamSession):
    """伪流式：累积 send_audio 的 chunk，stop() 时一次性调 recognize。

    对外协议与真流式一致（ready/final/None）。不产生 partial。
    """

    def __init__(
        self,
        backend: Qwen3AsrBackend,
        loop,
        sample_rate: int,
        language: str,
        queue_size: int,
    ):
        super().__init__(loop, queue_size=queue_size)
        self._backend = backend
        self._sample_rate = sample_rate
        self._language = language
        self._buffer = io.BytesIO()

    async def start(self) -> None:
        self._enqueue_threadsafe(AsrEvent(type="ready"))

    async def send_audio(self, chunk: bytes) -> None:
        self._buffer.write(chunk)

    async def stop(self) -> RecognitionResult:
        audio = self._buffer.getvalue()
        try:
            result = await self._backend.recognize(
                audio=audio,
                sample_rate=self._sample_rate,
                language=self._language,
                punctuation=True,
            )
        except Exception as e:
            logger.exception("qwen3 buffered stream stop failed")
            raise AsrBackendUnavailable(str(e)) from e
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
