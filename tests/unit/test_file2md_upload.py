from __future__ import annotations

import io
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

from spacemit_ai_gateway.common.streams import RequestBodySizeLimitMiddleware
from spacemit_ai_gateway.domains.file2md.api import _write_upload_to_temp
from spacemit_ai_gateway.domains.file2md.service import File2mdService


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
    assert not list(Path(tempfile.gettempdir()).glob("file2md-upload-*.txt"))


@pytest.mark.asyncio
async def test_empty_upload_is_rejected_before_temp_file_creation(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("empty uploads must not create a temporary file")

    monkeypatch.setattr(
        "spacemit_ai_gateway.domains.file2md.api.tempfile.NamedTemporaryFile",
        fail_if_called,
    )
    upload = UploadFile(file=io.BytesIO(b""), filename="empty.txt")
    with pytest.raises(HTTPException) as exc_info:
        await _write_upload_to_temp(upload, 10, "empty.txt")
    assert exc_info.value.status_code == 400


def test_manifest_error_keeps_engine_success_and_markdown():
    service = File2mdService(SimpleNamespace(provider="k3-int8"))
    service._engine = SimpleNamespace(
        convert=lambda path, options: SimpleNamespace(
            success=True,
            request_id="req-1",
            markdown="# Document",
            error="",
            manifest_json="{invalid",
            page_count=1,
            processing_time=1.5,
            output_directory="",
            middle_json="",
            content_list_json="",
            page_metrics=[],
        )
    )
    service._options = lambda overrides=None: None

    result = service._convert_sync("/tmp/input.pdf")

    assert result["success"] is True
    assert result["markdown"] == "# Document"
    assert result["manifest_error"]
    assert result["manifest_json_raw"] == "{invalid"


@pytest.mark.asyncio
async def test_request_body_middleware_rejects_chunked_body_before_app():
    called = False
    received_frames = 0
    sent = []

    async def app(scope, receive, send):
        nonlocal called, received_frames
        called = True
        while True:
            message = await receive()
            received_frames += 1
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
    assert received_frames == 1
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


@pytest.mark.asyncio
async def test_file2md_stats_reset_when_engine_is_unloaded_or_shutdown():
    service = File2mdService(SimpleNamespace(provider="k3-int8"))
    service._stats.update(
        total_requests=3,
        total_errors=1,
        total_processing_ms=42.0,
    )

    await service.unload_models()
    assert service.get_stats()["total_requests"] == 0
    assert service.get_stats()["total_errors"] == 0
    assert service.get_stats()["total_processing_ms"] == 0.0

    service._stats["total_requests"] = 1
    await service.shutdown()
    assert service.get_stats()["total_requests"] == 0


@pytest.mark.asyncio
async def test_healthz_returns_busy_without_waiting_for_conversion_lock():
    service = File2mdService(SimpleNamespace(provider="k3-int8"))
    service._state = "busy"
    await service._lock.acquire()
    try:
        result = await service.healthz()
    finally:
        service._lock.release()
    assert result["state"] == "busy"
    assert result["models"] == []
