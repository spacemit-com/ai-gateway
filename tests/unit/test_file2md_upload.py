from __future__ import annotations

import io

import pytest
from fastapi import HTTPException, UploadFile

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
