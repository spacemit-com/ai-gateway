"""Rerank backend 抽象基类。"""

from abc import ABC, abstractmethod


class RerankBackend(ABC):
    """Rerank backend 抽象接口。"""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Backend 名称。"""

    @abstractmethod
    async def proxy(
        self,
        path: str,
        request_body: bytes,
        headers: dict,
        stream: bool = False,
    ):
        """代理请求到 backend。

        Args:
            path: API 路径（如 /rerank）
            request_body: 请求体（原始字节）
            headers: 请求头
            stream: 是否流式响应

        Returns:
            httpx.Response
        """

    async def warmup(self) -> None:
        """预热 backend（可选）。"""

    async def shutdown(self) -> None:
        """关闭 backend（可选）。"""
