"""Embed adapter 工厂。"""

from ....app.settings import EmbedConfig
from .base import EmbedBackend
from .embed_backend import EmbedBackendImpl


def build_embed_backends(config: EmbedConfig) -> dict[str, EmbedBackend]:
    name = config.backend or "embed"
    return {name: EmbedBackendImpl(config=config)}


__all__ = [
    "EmbedBackend",
    "EmbedBackendImpl",
    "build_embed_backends",
]
