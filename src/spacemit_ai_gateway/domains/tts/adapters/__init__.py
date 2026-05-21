"""TTS adapter 工厂。"""

import logging

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

logger = logging.getLogger(__name__)

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
    if config.backends and set(config.backends) != {config.backend}:
        logger.warning(
            "tts.backends preloading is disabled; loading only default backend '%s'",
            config.backend,
        )
    return {config.backend: build_tts_backend(config)}


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
