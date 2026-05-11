"""TTS adapter 工厂。"""

from ....app.settings import TtsConfig
from .base import (
    TtsAudioChunk,
    TtsBackend,
    TtsChunk,
    TtsDone,
    TtsMetadata,
    TtsResult,
    TtsStreamSession,
)
from .kokoro import KokoroBackend
from .matcha import MatchaBackend

_REGISTRY = {
    "matcha_zh": MatchaBackend,
    "matcha_en": MatchaBackend,
    "matcha_zh_en": MatchaBackend,
    "kokoro": KokoroBackend,
}


def build_tts_backend(config: TtsConfig) -> TtsBackend:
    cls = _REGISTRY.get(config.backend)
    if cls is None:
        raise ValueError(f"unknown TTS backend: {config.backend}")
    return cls(config)


def build_tts_backends(config: TtsConfig) -> dict[str, TtsBackend]:
    names = config.backends if config.backends else [config.backend]
    result = {}
    for name in names:
        cls = _REGISTRY.get(name)
        if cls is None:
            raise ValueError(f"unknown TTS backend: {name}")
        backend_config = config.model_copy(update={"backend": name})
        result[name] = cls(backend_config)
    return result


TTS_REGISTRY = _REGISTRY

__all__ = [
    "TTS_REGISTRY",
    "TtsAudioChunk",
    "TtsBackend",
    "TtsChunk",
    "TtsDone",
    "TtsMetadata",
    "TtsResult",
    "TtsStreamSession",
    "build_tts_backend",
    "build_tts_backends",
]
