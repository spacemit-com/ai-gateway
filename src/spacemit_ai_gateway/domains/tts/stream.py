"""TTS WebSocket 传输层（/v1/tts/stream）。

鉴权：同 ASR，必须带 session_id（见 domains/asr/stream.py 模块 docstring）。

WS 协议：
    client → server:
        {"type":"start", "text":"..."}       # 可选 text，也可之后 append
        {"type":"append", "text":"..."}
        {"type":"end"}
    server → client:
        {"type":"ready"}
        <binary>                              # int16 PCM 块
        {"type":"metadata", "text":..., "timestamp_ms":...}
        {"type":"done", "duration_ms":..., "rtf":...}
        {"type":"error", "code":..., "message":..., "retriable":bool}
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket

from ...common.streams import ws_error_boundary
from ...gateway.dependencies import get_tts_stream_handler
from .adapters import TtsStreamSession
from .service import TtsService

logger = logging.getLogger(__name__)
router = APIRouter()


class TtsStreamHandler:
    def __init__(self, service: TtsService):
        self._service = service

    @ws_error_boundary
    async def handle(
        self,
        ws: WebSocket,
        session_id: Optional[str],
        voice_id: Optional[str],
        response_format: str,
    ) -> None:
        await ws.accept()

        session = await self._service.open_stream(
            session_id=session_id,
            voice_id=voice_id,
            response_format=response_format,
        )
        await session.start()
        await ws.send_json({"type": "ready"})

        pump_task = asyncio.create_task(
            _pump_chunks(session, ws), name="tts-ws-chunk-pump"
        )
        try:
            await _input_loop(session, ws)
            # input_loop 返回后，让 session 把剩余 chunk 刷出来
            await session.complete()
            await pump_task
        finally:
            if not pump_task.done():
                pump_task.cancel()


async def _input_loop(session: TtsStreamSession, ws: WebSocket) -> None:
    while True:
        msg = await ws.receive()
        mtype = msg.get("type")
        if mtype == "websocket.disconnect":
            return
        if mtype != "websocket.receive":
            continue
        text_frame = msg.get("text")
        if text_frame is None:
            continue
        try:
            data = json.loads(text_frame)
        except json.JSONDecodeError:
            continue

        kind = data.get("type")
        if kind in ("start", "append"):
            text = data.get("text") or ""
            if text:
                await session.send_text(text)
        elif kind == "end":
            return


async def _pump_chunks(session: TtsStreamSession, ws: WebSocket) -> None:
    while True:
        chunk = await session.recv()
        if chunk is None:
            return
        kind, payload = chunk.to_message()
        try:
            if kind == "binary":
                await ws.send_bytes(payload)
            else:
                await ws.send_json(payload)
        except Exception:
            logger.debug("tts ws send failed", exc_info=True)
            return


@router.websocket("/stream")
async def stream_synthesize(
    websocket: WebSocket,
    session_id: Optional[str] = Query(default=None),
    voice_id: Optional[str] = Query(default=None),
    response_format: str = Query(default="pcm"),
    handler: TtsStreamHandler = Depends(get_tts_stream_handler),
):
    await handler.handle(
        websocket,
        session_id=session_id,
        voice_id=voice_id,
        response_format=response_format,
    )
