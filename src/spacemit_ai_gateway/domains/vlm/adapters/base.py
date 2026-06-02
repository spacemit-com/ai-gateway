"""VLM backend contract."""

from abc import ABC, abstractmethod


class VlmBackend(ABC):
    """VLM backend contract."""

    @property
    @abstractmethod
    def backend_name(self) -> str: ...

    @abstractmethod
    async def proxy_for(self, model_id: str, source_type: str,
                        path: str, request_body: bytes, headers: dict, stream: bool = False): ...

    async def warmup(self) -> None:
        """Default no-op."""

    async def shutdown(self) -> None:
        """Release backend resources."""
