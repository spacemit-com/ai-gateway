"""FastAPI 依赖注入入口。

api / stream 路由只通过这里获取 service / handler，不再读 app.state。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request, WebSocket

from ..common.errors import ServiceUnavailableError

if TYPE_CHECKING:
    from ..domains.asr.service import AsrService
    from ..domains.asr.stream import AsrStreamHandler
    from ..domains.tts.service import TtsService
    from ..domains.tts.stream import TtsStreamHandler
    from ..domains.vad.service import VadService
    from ..domains.vad.stream import VadStreamHandler


def _state_attr(obj, name: str, domain: str):
    value = getattr(obj.state, name, None)
    if value is None:
        raise ServiceUnavailableError(f"{domain} service not initialized")
    return value


# ---- ASR ----
def get_asr_service(request: Request) -> "AsrService":
    return _state_attr(request.app, "asr_service", "ASR")


def get_asr_stream_handler(websocket: WebSocket) -> "AsrStreamHandler":
    return _state_attr(websocket.app, "asr_stream_handler", "ASR")


# ---- TTS ----
def get_tts_service(request: Request) -> "TtsService":
    return _state_attr(request.app, "tts_service", "TTS")


def get_tts_stream_handler(websocket: WebSocket) -> "TtsStreamHandler":
    return _state_attr(websocket.app, "tts_stream_handler", "TTS")


# ---- VAD ----
def get_vad_service(request: Request) -> "VadService":
    return _state_attr(request.app, "vad_service", "VAD")


def get_vad_stream_handler(websocket: WebSocket) -> "VadStreamHandler":
    return _state_attr(websocket.app, "vad_stream_handler", "VAD")
