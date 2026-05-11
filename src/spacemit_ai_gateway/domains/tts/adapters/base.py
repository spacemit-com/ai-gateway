"""TTS Backend ABC + StreamSession ABC。

与 ASR 同构；流式事件用单一 tagged union（P1-9）：audio / metadata / done。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from ....common.ready_state import BackendReadyState
from ....common.schemas import ModelInfo, VoiceInfo
from ....common.streams import StreamSessionBase


@dataclass
class TtsResult:
    """同步合成结果。audio 为 int16 单声道 PCM。"""

    audio: np.ndarray
    sample_rate: int
    duration_ms: float = 0.0
    processing_ms: float = 0.0
    rtf: float = 0.0


# ----- tagged union -----

@dataclass
class TtsAudioChunk:
    pcm: bytes
    seq: int = 0
    type: str = "audio"

    def to_message(self) -> tuple[str, object]:
        return "binary", self.pcm


@dataclass
class TtsMetadata:
    text: str = ""
    timestamp_ms: float = 0.0
    type: str = "metadata"

    def to_message(self) -> tuple[str, object]:
        return "json", {
            "type": "metadata",
            "text": self.text,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass
class TtsDone:
    duration_ms: float = 0.0
    rtf: float = 0.0
    type: str = "done"

    def to_message(self) -> tuple[str, object]:
        return "json", {
            "type": "done",
            "duration_ms": self.duration_ms,
            "rtf": self.rtf,
        }


TtsChunk = TtsAudioChunk | TtsMetadata | TtsDone


class TtsStreamSession(StreamSessionBase[TtsChunk], ABC):
    """一次 WS 合成会话。"""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def send_text(self, text: str) -> None: ...

    @abstractmethod
    async def complete(self) -> None: ...

    async def recv(self) -> Optional[TtsChunk]:
        return await self._recv()


class TtsBackend(ABC):
    @property
    @abstractmethod
    def backend_name(self) -> str: ...

    @property
    @abstractmethod
    def sample_rate(self) -> int: ...

    @property
    @abstractmethod
    def state(self) -> BackendReadyState: ...

    @property
    def is_ready(self) -> bool:
        return self.state.is_serving

    @abstractmethod
    async def synthesize(
        self, text: str, voice_id: Optional[str], speed: float, pitch: float, volume: float
    ) -> TtsResult: ...

    @abstractmethod
    async def open_stream(
        self, voice_id: Optional[str], speed: float
    ) -> TtsStreamSession: ...

    @abstractmethod
    def get_voices(self) -> List[VoiceInfo]: ...

    @abstractmethod
    def get_models(self) -> List[ModelInfo]: ...

    def get_params(self) -> dict:
        return {}

    def get_engine_config(self) -> dict:
        return {}

    async def warmup(self) -> None: ...
    async def shutdown(self) -> None: ...
