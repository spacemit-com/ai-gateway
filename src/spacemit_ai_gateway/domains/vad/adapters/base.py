"""VAD Backend ABC + StreamSession ABC。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from ....common.ready_state import BackendReadyState
from ....common.streams import StreamSessionBase


@dataclass
class VadAnalysis:
    is_speech: bool
    probability: float
    smoothed_probability: Optional[float] = None
    processing_ms: float = 0.0


@dataclass
class Segment:
    start_ms: float
    end_ms: float
    confidence: float


@dataclass
class VadEvent:
    """流式事件。type 取值：speech_start / speech_end / speech / silence / error。"""

    event: str
    probability: float = 0.0
    timestamp_ms: float = 0.0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "event": self.event,
            "probability": self.probability,
            "timestamp_ms": self.timestamp_ms,
        }
        d.update(self.extra)
        return d


class VadStreamSession(StreamSessionBase[VadEvent], ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    async def recv_event(self) -> Optional[VadEvent]:
        return await self._recv()


class VadBackend(ABC):
    @property
    @abstractmethod
    def backend_name(self) -> str: ...

    @property
    @abstractmethod
    def state(self) -> BackendReadyState: ...

    @property
    def is_ready(self) -> bool:
        return self.state.is_serving

    @abstractmethod
    async def analyze(self, audio: bytes, sample_rate: int) -> VadAnalysis: ...

    @abstractmethod
    async def segment(self, audio: bytes, sample_rate: int) -> tuple[List[Segment], float]:
        """返回 (segments, duration_ms)。"""

    @abstractmethod
    async def open_stream(self, sample_rate: int) -> VadStreamSession: ...

    @abstractmethod
    def get_params(self) -> dict: ...

    def get_audio_config(self) -> dict:
        return {}

    def get_engine_config(self) -> dict:
        return {}

    async def warmup(self) -> None: ...
    async def shutdown(self) -> None: ...
