"""VLM adapter factory."""

from ....app.settings import VlmConfig
from .base import VlmBackend
from .vlm_backend import VlmBackendImpl


def build_vlm_backends(config: VlmConfig) -> dict[str, VlmBackend]:
    name = config.backend or "vlm"
    return {name: VlmBackendImpl(config=config)}


__all__ = [
    "VlmBackend",
    "VlmBackendImpl",
    "build_vlm_backends",
]
