"""ASR WebSocket 传输层（/v1/asr/stream）。

鉴权流程（P2-12）：
1. 客户端先 POST /v1/asr/stream/session，经 verify_api_key 签发 session_id
2. 服务端把 session_id 存入 SessionStore（默认 TTL 5 分钟）
3. WS 握手：ws://.../v1/asr/stream?session_id=<id>&language=...&sample_rate=...&partial=...
4. 本模块从 SessionStore 取出 session 记录；取不到 → InvalidSessionError → close(1011)

不接受无 session_id 的 WS 连接（浏览器 WS API 无法设 custom header，
query token 有日志泄露风险，subprotocol 难维护）。

WS 协议:
    client → server:
        binary     : PCM 音频帧
        json text  : {"type":"end"}
    server → client:
        {"type":"ready"}
        {"type":"partial", "text": ...}
        {"type":"sentence_end", "text": ...}
        {"type":"final", "text":..., "duration_ms":..., "rtf":...}
        {"type":"error", "code":..., "message":..., "retriable":bool}
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket

from ...common.streams import ws_error_boundary
from ...gateway.dependencies import get_asr_stream_handler
from .adapters import AsrStreamSession
from .service import AsrService

logger = logging.getLogger(__name__)
router = APIRouter()


class AsrStreamHandler:
    def __init__(self, service: AsrService):
        self._service = service

    @ws_error_boundary
    async def handle(
        self,
        ws: WebSocket,
        session_id: Optional[str],
        language: str,
        sample_rate: int,
        partial: bool,
        enable_emotion: Optional[bool],
    ) -> None:
        await ws.accept()

        session = await self._service.open_stream(
            session_id=session_id,
            language=language,
            sample_rate=sample_rate,
            partial=partial,
            enable_emotion=enable_emotion,
        )
        await session.start()

        event_task = None
        try:
            event_task = _spawn_event_pump(session, ws)
            await _input_loop(session, ws)
        finally:
            try:
                await session.stop()
            except Exception:
                logger.debug("session.stop failed", exc_info=True)
            if event_task is not None:
                event_task.cancel()


async def _input_loop(session: AsrStreamSession, ws: WebSocket) -> None:
    while True:
        msg = await ws.receive()
        mtype = msg.get("type")
        if mtype == "websocket.disconnect":
            return
        if mtype != "websocket.receive":
            continue

        if "bytes" in msg and msg["bytes"] is not None:
            await session.send_audio(msg["bytes"])
        elif "text" in msg and msg["text"] is not None:
            try:
                data = json.loads(msg["text"])
            except json.JSONDecodeError:
                continue
            if data.get("type") == "end":
                return


def _spawn_event_pump(session: AsrStreamSession, ws: WebSocket):
    import asyncio

    async def _pump():
        while True:
            ev = await session.recv_event()
            if ev is None:
                return
            try:
                await ws.send_json(ev.to_dict())
            except Exception:
                logger.debug("ws.send_json failed, stopping pump", exc_info=True)
                return

    return asyncio.create_task(_pump(), name="asr-ws-event-pump")


@router.websocket("/stream")
async def stream_recognize(
    websocket: WebSocket,
    session_id: Optional[str] = Query(default=None),
    language: str = Query(default="auto"),
    sample_rate: int = Query(default=16000),
    partial: bool = Query(default=True),
    enable_emotion: Optional[bool] = Query(default=None),
    handler: AsrStreamHandler = Depends(get_asr_stream_handler),
):
    await handler.handle(
        websocket,
        session_id=session_id,
        language=language,
        sample_rate=sample_rate,
        partial=partial,
        enable_emotion=enable_emotion,
    )
