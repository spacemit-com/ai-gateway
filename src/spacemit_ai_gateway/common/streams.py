"""WebSocket / HTTP 流辅助。

- ws_error_boundary: WS handler 装饰器，统一 DomainError → {"type":"error"} + close(1011)
- enforce_max_upload_size: HTTP dependency，按 Content-Length 拦截过大请求
- StreamSessionBase: 三个域 stream session 的公共基类，处理跨线程事件入队、背压、recv
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Awaitable, Callable, Generic, Optional, TypeVar

from fastapi import Request, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from .errors import DomainError, RequestTooLargeError

logger = logging.getLogger(__name__)


# ============================================================
# WS 异常边界
# ============================================================

def ws_error_boundary(handler: Callable[..., Awaitable[None]]):
    """装饰 WS handler：

    - DomainError → send_json({"type":"error", ...}) + close(1011)
    - WebSocketDisconnect → 忽略（客户端主动断开）
    - 其它异常 → log.exception + close(1011, "internal error")

    注意：装饰器假设 handler 已经调用过 `await ws.accept()`。如果没 accept
    就抛 DomainError，close 会静默失败但不会崩。
    """

    @functools.wraps(handler)
    async def wrapped(self, ws: WebSocket, *args, **kwargs):
        try:
            await handler(self, ws, *args, **kwargs)
        except DomainError as e:
            logger.info("WS domain error in %s: %s", handler.__qualname__, e.message)
            await _safe_send_error(ws, e.code, e.message, retriable=e.retriable)
            await _safe_close(ws, code=1011)
        except WebSocketDisconnect:
            logger.debug("WS client disconnected in %s", handler.__qualname__)
        except Exception:
            logger.exception("unhandled WS error in %s", handler.__qualname__)
            await _safe_close(ws, code=1011, reason="internal error")

    return wrapped


async def _safe_send_error(
    ws: WebSocket, code: str, message: str, *, retriable: bool = False
) -> None:
    if ws.client_state != WebSocketState.CONNECTED:
        return
    try:
        await ws.send_json(
            {"type": "error", "code": code, "message": message, "retriable": retriable}
        )
    except Exception:
        logger.debug("failed to send error frame", exc_info=True)


async def _safe_close(ws: WebSocket, *, code: int, reason: str = "") -> None:
    if ws.client_state == WebSocketState.DISCONNECTED:
        return
    try:
        await ws.close(code=code, reason=reason or None)
    except Exception:
        logger.debug("failed to close websocket", exc_info=True)


# ============================================================
# HTTP 上传大小限制
# ============================================================

def enforce_max_upload_size(max_bytes: int) -> Callable[[Request], Awaitable[None]]:
    """工厂：返回一个 FastAPI dependency，按 `Content-Length` 拒绝过大请求。

    用法：
        _: None = Depends(enforce_max_upload_size(settings.limits.max_upload_bytes))
    """

    async def dep(request: Request) -> None:
        cl = request.headers.get("content-length")
        if cl is None:
            return
        try:
            size = int(cl)
        except ValueError:
            return
        if size > max_bytes:
            raise RequestTooLargeError(
                f"upload size {size} bytes exceeds limit {max_bytes} bytes"
            )

    return dep


# ============================================================
# StreamSessionBase：三个域 stream session 公共基类
# ============================================================

E = TypeVar("E")


class StreamSessionBase(Generic[E]):
    """处理 SDK 回调线程 → asyncio 事件循环的安全桥接。

    关键硬约定：
    - loop 必须在主事件循环线程里捕获（__init__ 期间调用 get_running_loop）
    - SDK 回调里只能调 `self._enqueue_threadsafe(event)`，**不能** put_nowait
    - `None` 作为 sentinel 表示流结束；recv 返回 None 后不应再调 recv

    背压策略：
    - final / error / sentinel 等关键事件：永远入队，必要时丢最旧 partial 腾位
    - partial：队列满直接丢弃，递增 _dropped_partial 计数
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, queue_size: int = 64):
        self._loop = loop
        self._queue: asyncio.Queue[Optional[E]] = asyncio.Queue(maxsize=queue_size)
        self._closed = False
        self._dropped_partial = 0

    @property
    def dropped_partial_count(self) -> int:
        return self._dropped_partial

    def _enqueue_threadsafe(self, event: Optional[E]) -> None:
        """SDK 回调线程调用。线程安全。"""
        self._loop.call_soon_threadsafe(self._enqueue, event)

    def _enqueue(self, event: Optional[E]) -> None:
        """事件循环线程执行。按背压策略入队。"""
        if self._closed and event is not None:
            return
        if event is None:
            self._closed = True

        try:
            self._queue.put_nowait(event)
            return
        except asyncio.QueueFull:
            pass

        # 队列满：
        if self._is_partial(event):
            self._dropped_partial += 1
            return
        # 关键事件必须入队：丢最旧的 partial 腾位；若没有可丢的，丢队头
        self._drain_one_partial_or_head()
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("stream queue still full after draining; event dropped")

    def _drain_one_partial_or_head(self) -> None:
        # 简化实现：snapshot 队列，丢第一个 partial；找不到就丢队头
        items: list[Optional[E]] = []
        dropped = False
        while not self._queue.empty():
            items.append(self._queue.get_nowait())
        for item in items:
            if not dropped and self._is_partial(item):
                self._dropped_partial += 1
                dropped = True
                continue
            # 其它按原序放回
            try:
                self._queue.put_nowait(item)
            except asyncio.QueueFull:
                break
        if not dropped and items:
            # 没 partial 可丢，退而求其次：队头已在 put 循环中被 break 丢弃
            logger.debug("drained head of stream queue to make room")

    def _is_partial(self, event: Optional[E]) -> bool:
        """子类可覆写。默认识别 dict / pydantic / 含 `type` 属性的对象。"""
        if event is None:
            return False
        t = getattr(event, "type", None)
        if t is None and isinstance(event, dict):
            t = event.get("type")
        return t == "partial"

    async def _recv(self) -> Optional[E]:
        return await self._queue.get()
