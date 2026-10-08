"""推理后端响应透传。"""

from __future__ import annotations

import json
from typing import AsyncIterator, Callable, Optional

import httpx
from fastapi.responses import JSONResponse, Response

from .errors import DomainError


def passthrough_response(
    content: bytes, response: httpx.Response, request_id: Optional[str] = None
) -> Response:
    """后端返回 JSON 时原样返回（含引擎自己的错误体）。

    非 JSON 的错误响应（如远程 API 返回 HTML 404）归为 upstream_error，
    以前这里直接 json.loads 会抛异常变成 500 internal_error。
    """
    headers = {"X-Request-ID": request_id} if request_id else None
    try:
        parsed = json.loads(content)
    except ValueError:
        if response.status_code >= 400:
            raise DomainError(
                f"backend returned HTTP {response.status_code} with a non-JSON body",
                code="upstream_error",
                status_code=502,
                retriable=response.status_code >= 500,
                details={
                    "upstream_status": response.status_code,
                    "body": content[:300].decode("utf-8", errors="replace"),
                },
            )
        return Response(
            content=content,
            status_code=response.status_code,
            media_type=response.headers.get("content-type", "application/octet-stream"),
            headers=headers,
        )
    return JSONResponse(content=parsed, status_code=response.status_code, headers=headers)


# ---------------------------------------------------------------------------
# 流式响应中途失败
# ---------------------------------------------------------------------------

class _ClassifiedStream(httpx.AsyncByteStream):
    """读流时连接断开（推理进程崩溃、远程 API 断开）转成分类后的 DomainError。"""

    def __init__(self, inner: httpx.AsyncByteStream, to_error: Callable[[httpx.TransportError], DomainError]):
        self._inner = inner
        self._to_error = to_error

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._inner:
                yield chunk
        except httpx.TransportError as exc:
            raise self._to_error(exc) from exc

    async def aclose(self) -> None:
        await self._inner.aclose()


def classify_stream_errors(
    response: httpx.Response, to_error: Callable[[httpx.TransportError], DomainError]
) -> None:
    response.stream = _ClassifiedStream(response.stream, to_error)


def stream_protocol(path: str) -> str:
    if path == "/v1/messages":
        return "anthropic"
    if path == "/v1/responses":
        return "responses"
    return "openai"


def stream_error_frame(exc: DomainError, protocol: str) -> bytes:
    """响应头已发出后改不了 HTTP 状态码：按各协议自己的流内错误约定补一帧，带上 gateway 错误码。"""
    fields = {"code": exc.code, "message": exc.message, "retriable": exc.retriable, "details": exc.details}
    if protocol == "ollama":
        body = {"error": exc.message, **fields, "done": True}
        return json.dumps(body, ensure_ascii=False).encode() + b"\n"
    if protocol == "anthropic":
        body = {"type": "error", "error": {"type": "api_error", **fields}}
        return b"event: error\ndata: " + json.dumps(body, ensure_ascii=False).encode() + b"\n\n"
    if protocol == "responses":
        body = {"type": "error", **fields}
        return b"event: error\ndata: " + json.dumps(body, ensure_ascii=False).encode() + b"\n\n"
    body = {"error": {"type": "server_error", **fields}}
    return b"data: " + json.dumps(body, ensure_ascii=False).encode() + b"\n\n"
