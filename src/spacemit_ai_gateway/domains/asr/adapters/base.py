"""ASR Backend ABC + StreamSession ABC。

跨线程硬约定：
- SDK 回调（AsrCallback.on_event 等）在 C++ 线程里执行
- **必须**通过 `self._enqueue_threadsafe(event)` 入队，不能直接 put_nowait
- 基类 `StreamSessionBase` 已封装 loop.call_soon_threadsafe 桥接逻辑
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from ....common.ready_state import BackendReadyState
from ....common.schemas import ModelInfo
from ....common.streams import StreamSessionBase


@dataclass
class RecognitionResult:
    """同步识别结果。"""

    text: str
    sentences: list[dict] = field(default_factory=list)
    duration_ms: float = 0.0
    processing_ms: float = 0.0
    rtf: float = 0.0
    language: Optional[str] = None


@dataclass
class AsrEvent:
    """流式事件 tagged union。"""

    type: str  # "ready" | "partial" | "sentence_end" | "final" | "error"
    text: str = ""
    duration_ms: float = 0.0
    rtf: float = 0.0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"type": self.type}
        if self.text:
            d["text"] = self.text
        if self.duration_ms:
            d["duration_ms"] = self.duration_ms
        if self.rtf:
            d["rtf"] = self.rtf
        d.update(self.extra)
        return d


class AsrStreamSession(StreamSessionBase[AsrEvent], ABC):
    """一次 WS 会话。send_audio / flush / stop 由子类实现。

    子类在 SDK 回调里调 `self._enqueue_threadsafe(AsrEvent(...))`。
    正常结束时调 `self._enqueue_threadsafe(None)` 标记流终止。
    """

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None: ...

    @abstractmethod
    async def stop(self) -> RecognitionResult: ...

    async def recv_event(self) -> Optional[AsrEvent]:
        return await self._recv()


class AsrBackend(ABC):
    """ASR backend 契约。"""

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
    async def recognize(
        self,
        audio: bytes,
        sample_rate: int,
        language: str,
        punctuation: bool,
        hotwords: Optional[List[str]] = None,
    ) -> RecognitionResult: ...

    @abstractmethod
    async def create_stream(
        self,
        sample_rate: int,
        language: str,
        partial: bool,
    ) -> AsrStreamSession: ...

    @abstractmethod
    def get_supported_languages(self) -> List[str]: ...

    @abstractmethod
    def get_models(self) -> List[ModelInfo]: ...

    def get_params(self) -> dict:
        return {}

    def get_audio_config(self) -> dict:
        return {}

    def get_engine_config(self) -> dict:
        return {}

    async def warmup(self) -> None:
        """默认空实现。真实 backend 可以在这里 trigger 首次推理。"""

    async def shutdown(self) -> None:
        """释放资源。"""
