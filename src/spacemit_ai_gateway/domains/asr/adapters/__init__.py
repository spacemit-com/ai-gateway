"""ASR adapter 工厂。"""

from ....app.settings import AsrConfig
from .base import AsrBackend, AsrEvent, AsrStreamSession, RecognitionResult
from .sensevoice import SenseVoiceBackend
from .qwen3_asr import Qwen3AsrBackend

_REGISTRY = {
    "sensevoice": SenseVoiceBackend,
    "qwen3-asr": Qwen3AsrBackend,
}


def build_asr_backend(config: AsrConfig) -> AsrBackend:
    cls = _REGISTRY.get(config.backend)
    if cls is None:
        raise ValueError(f"unknown ASR backend: {config.backend}")
    return cls(config)


def build_asr_backends(config: AsrConfig) -> dict[str, AsrBackend]:
    names = config.backends if config.backends else [config.backend]
    result = {}
    for name in names:
        cls = _REGISTRY.get(name)
        if cls is None:
            raise ValueError(f"unknown ASR backend: {name}")
        backend_config = config.model_copy(update={"backend": name})
        result[name] = cls(backend_config)
    return result


ASR_REGISTRY = _REGISTRY

__all__ = [
    "ASR_REGISTRY",
    "AsrBackend",
    "AsrEvent",
    "AsrStreamSession",
    "RecognitionResult",
    "build_asr_backend",
    "build_asr_backends",
]
