"""LLM adapter 工厂。"""

from ....app.settings import LlmConfig
from .base import LlmBackend
from .llm_backend import LlmBackendImpl


def build_llm_backends(config: LlmConfig) -> dict[str, LlmBackend]:
    name = config.backend or "llm"
    return {name: LlmBackendImpl(config=config)}


__all__ = [
    "LlmBackend",
    "LlmBackendImpl",
    "build_llm_backends",
]
