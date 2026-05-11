"""VAD adapter 工厂。"""

from ....app.settings import VadConfig
from .base import Segment, VadAnalysis, VadBackend, VadEvent, VadStreamSession
from .silero import SileroBackend

_REGISTRY = {
    "silero": SileroBackend,
}


def build_vad_backend(config: VadConfig) -> VadBackend:
    cls = _REGISTRY.get(config.backend)
    if cls is None:
        raise ValueError(f"unknown VAD backend: {config.backend}")
    return cls(config)


VAD_REGISTRY = _REGISTRY


def build_vad_backends(config: VadConfig) -> dict[str, VadBackend]:
    names = config.backends if config.backends else [config.backend]
    result = {}
    for name in names:
        cls = _REGISTRY.get(name)
        if cls is None:
            raise ValueError(f"unknown VAD backend: {name}")
        backend_config = config.model_copy(update={"backend": name})
        result[name] = cls(backend_config)
    return result


__all__ = [
    "Segment",
    "VAD_REGISTRY",
    "VadAnalysis",
    "VadBackend",
    "VadEvent",
    "VadStreamSession",
    "build_vad_backend",
    "build_vad_backends",
]
