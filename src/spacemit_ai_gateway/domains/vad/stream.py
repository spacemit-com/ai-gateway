"""VAD WebSocket 传输层（/v1/vad/stream）。

VAD 无会话（流式无鉴权记录要查），WS 握手只校 verify_api_key 不带 session_id。
不过浏览器 WS API 无法传 API key header——如果未来要对 WS 加鉴权，
按 ASR 模式补 /stream/session 即可。

WS 协议：
    client → server:
        binary : PCM 音频帧（建议 30ms 一帧）
        json text: {"type":"end"}
    server → client:
        {"type":"ready"}
        {"event":"speech_start|speech_end|speech|silence", "probability":..., "timestamp_ms":...}
        {"type":"error", ...}
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket

from ...common.streams import ws_error_boundary
from ...gateway.dependencies import get_vad_stream_handler
from .adapters import VadStreamSession
from .service import VadService

logger = logging.getLogger(__name__)
router = APIRouter()


class VadStreamHandler:
    def __init__(self, service: VadService):
        self._service = service

    @ws_error_boundary
    async def handle(self, ws: WebSocket, sample_rate: int) -> None:
        await ws.accept()

        session = await self._service.open_stream(sample_rate=sample_rate)
        await session.start()
        await ws.send_json({"type": "ready"})

        pump = asyncio.create_task(_pump(session, ws), name="vad-ws-pump")
        try:
            await _input_loop(session, ws)
        finally:
            try:
                await session.stop()
            except Exception:
                logger.debug("session.stop failed", exc_info=True)
            if not pump.done():
                try:
                    await asyncio.wait_for(pump, timeout=0.5)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pump.cancel()


async def _input_loop(session: VadStreamSession, ws: WebSocket) -> None:
    while True:
        msg = await ws.receive()
        mtype = msg.get("type")
        if mtype == "websocket.disconnect":
            return
        if mtype != "websocket.receive":
            continue
        if msg.get("bytes") is not None:
            await session.send_audio(msg["bytes"])
        elif msg.get("text") is not None:
            try:
                data = json.loads(msg["text"])
            except json.JSONDecodeError:
                continue
            if data.get("type") == "end":
                return


async def _pump(session: VadStreamSession, ws: WebSocket) -> None:
    while True:
        ev = await session.recv_event()
        if ev is None:
            return
        try:
            await ws.send_json(ev.to_dict())
        except Exception:
            logger.debug("vad ws send failed", exc_info=True)
            return


@router.websocket("/stream")
async def stream_detect(
    websocket: WebSocket,
    sample_rate: int = Query(default=16000),
    handler: VadStreamHandler = Depends(get_vad_stream_handler),
):
    await handler.handle(websocket, sample_rate=sample_rate)
