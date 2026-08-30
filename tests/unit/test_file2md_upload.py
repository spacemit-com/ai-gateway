from __future__ import annotations

import io

import pytest
from fastapi import HTTPException, UploadFile

from spacemit_ai_gateway.common.streams import RequestBodySizeLimitMiddleware
from spacemit_ai_gateway.domains.file2md.api import _write_upload_to_temp


@pytest.mark.asyncio
async def test_chunked_upload_is_written_in_bounded_file(tmp_path):
    upload = UploadFile(file=io.BytesIO(b"hello" * 1000), filename="note.txt")
    path = await _write_upload_to_temp(upload, 10_000, "note.txt")
    try:
        assert path.suffix == ".txt"
        assert path.read_bytes() == b"hello" * 1000
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_chunked_upload_hard_limit_returns_413():
    upload = UploadFile(file=io.BytesIO(b"x" * 11), filename="note.txt")
    with pytest.raises(HTTPException) as exc_info:
        await _write_upload_to_temp(upload, 10, "note.txt")
    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_request_body_middleware_rejects_chunked_body_before_app():
    called = False
    sent = []

    async def app(scope, receive, send):
        nonlocal called
        called = True
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            if not message.get("more_body"):
                return

    messages = iter(
        [
            {"type": "http.request", "body": b"x" * 8, "more_body": True},
            {"type": "http.request", "body": b"y" * 8, "more_body": False},
        ]
    )

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    middleware = RequestBodySizeLimitMiddleware(app, max_bytes=10)
    await middleware(
        {
            "type": "http",
            "path": "/v1/file2md/convert",
            "headers": [(b"transfer-encoding", b"chunked")],
        },
        receive,
        send,
    )

    assert called is True
    assert sent[-2]["status"] == 413
    assert sent[-1]["body"]


@pytest.mark.asyncio
async def test_request_body_middleware_rejects_declared_body_before_app():
    called = False
    sent = []

    async def app(scope, receive, send):
        nonlocal called
        called = True

    async def send(message):
        sent.append(message)

    middleware = RequestBodySizeLimitMiddleware(app, max_bytes=10)
    await middleware(
        {
            "type": "http",
            "path": "/v1/file2md/convert",
            "headers": [(b"content-length", b"11")],
        },
        lambda: None,
        send,
    )

    assert called is False
    assert sent[-2]["status"] == 413
