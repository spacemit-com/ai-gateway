"""LLM Backend ABC。"""

from abc import ABC, abstractmethod


class LlmBackend(ABC):
    """LLM backend 契约。"""

    @property
    @abstractmethod
    def backend_name(self) -> str: ...

    @abstractmethod
    async def proxy(self, path: str, request_body: bytes, headers: dict, stream: bool = False): ...

    async def warmup(self) -> None:
        """默认空实现。"""

    async def shutdown(self) -> None:
        """释放资源。"""
