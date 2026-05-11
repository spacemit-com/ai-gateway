"""Rerank adapter 工厂。"""

from ....app.settings import RerankConfig
from .base import RerankBackend
from .rerank_backend import RerankBackendImpl


def build_rerank_backends(config: RerankConfig) -> dict[str, RerankBackend]:
    name = config.backend or "rerank"
    return {name: RerankBackendImpl(config=config)}


__all__ = [
    "RerankBackend",
    "RerankBackendImpl",
    "build_rerank_backends",
]
